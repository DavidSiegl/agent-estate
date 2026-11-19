// Tests claude-hooks.ts against a scratch plugin whose hooks are small bash
// scripts, and against this plugin's own hooks.json for the review gate's
// guard. Run: node --test plugins/agent-estate/pi/claude-hooks_test.ts
import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { type HookInput, loadHooks } from "./claude-hooks.ts";

const here = dirname(fileURLToPath(import.meta.url));

/** A plugin root holding hooks.json (as `hooks`) and the named executable scripts in hooks/. */
async function plugin(hooks: object, scripts: Record<string, string>): Promise<string> {
	const root = await mkdtemp(join(tmpdir(), "claude-hooks-test-"));
	await mkdir(join(root, "hooks"));
	await writeFile(join(root, "hooks", "hooks.json"), JSON.stringify({ hooks }));
	for (const [name, body] of Object.entries(scripts)) {
		const path = join(root, "hooks", name);
		await writeFile(path, `#!/usr/bin/env bash\n${body}\n`);
		await chmod(path, 0o755);
	}
	return root;
}

const cmd = (name: string, timeout?: number) => ({ type: "command", command: `"\${CLAUDE_PLUGIN_ROOT}/hooks/${name}"`, timeout });

function tool(event: "PreToolUse" | "PostToolUse", name: string, input: Record<string, unknown>): HookInput {
	return { hook_event_name: event, session_id: "s1", cwd: tmpdir(), tool_name: name, tool_input: input };
}

test("a matcher selects by exact name, |-list or regex", async () => {
	const root = await plugin(
		{
			PreToolUse: [
				{ matcher: "Bash", hooks: [cmd("say.sh")] },
				{ matcher: "Write|Edit", hooks: [cmd("say.sh")] },
				{ hooks: [cmd("say.sh")] },
			],
			SessionStart: [{ matcher: "^(clear|compact)$", hooks: [cmd("say.sh")] }],
		},
		{ "say.sh": `jq -c '{hookSpecificOutput: {additionalContext: .hook_event_name}}'` },
	);
	const run = await loadHooks(root);
	assert.equal((await run(tool("PreToolUse", "Bash", {}))).context.length, 2);
	assert.equal((await run(tool("PreToolUse", "Edit", {}))).context.length, 2);
	assert.equal((await run(tool("PreToolUse", "Read", {}))).context.length, 1);
	assert.equal((await run(tool("PreToolUse", "Bashful", {}))).context.length, 1);
	const start = (source: HookInput["source"]): HookInput => ({ hook_event_name: "SessionStart", session_id: "s1", cwd: tmpdir(), source });
	assert.deepEqual((await run(start("compact"))).context, ["SessionStart"]);
	assert.deepEqual((await run(start("startup"))).context, []);
});

test("a hook reads the input on stdin and runs in its cwd with the plugin's variables", async () => {
	const root = await plugin(
		{ PostToolUse: [{ hooks: [cmd("echo.sh")] }] },
		{ "echo.sh": `jq -c --arg pwd "$PWD" --arg root "$CLAUDE_PLUGIN_ROOT" --arg proj "$CLAUDE_PROJECT_DIR" '{hookSpecificOutput: {additionalContext: ([.tool_input.file_path, $pwd, $root, $proj] | join(" "))}}'` },
	);
	const cwd = await mkdtemp(join(tmpdir(), "claude-hooks-cwd-"));
	const out = await (await loadHooks(root))({ ...tool("PostToolUse", "Read", { file_path: "/x" }), cwd });
	assert.deepEqual(out.context, [`/x ${cwd} ${root} ${cwd}`]);
});

test("exit 2 refuses a tool call with stderr; a deny decision refuses too; both reasons are kept", async () => {
	const root = await plugin(
		{ PreToolUse: [{ hooks: [cmd("no.sh"), cmd("deny.sh")] }] },
		{
			"no.sh": `echo "not like that" >&2; exit 2`,
			"deny.sh": `echo '{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "nor that"}}'`,
		},
	);
	const out = await (await loadHooks(root))(tool("PreToolUse", "Bash", { command: "x" }));
	assert.equal(out.refusal, "not like that\n\nnor that");
});

test("exit 2 after a tool ran is context, not a refusal", async () => {
	const root = await plugin({ PostToolUse: [{ hooks: [cmd("no.sh")] }] }, { "no.sh": `echo "look again" >&2; exit 2` });
	const out = await (await loadHooks(root))(tool("PostToolUse", "Write", {}));
	assert.equal(out.refusal, undefined);
	assert.deepEqual(out.context, ["look again"]);
});

test("plain stdout is context at session start and on a prompt, and ignored around a tool", async () => {
	const root = await plugin(
		{ SessionStart: [{ hooks: [cmd("say.sh")] }], UserPromptSubmit: [{ hooks: [cmd("say.sh")] }], PreToolUse: [{ hooks: [cmd("say.sh")] }] },
		{ "say.sh": `echo hello` },
	);
	const run = await loadHooks(root);
	assert.deepEqual((await run({ hook_event_name: "SessionStart", session_id: "s", cwd: tmpdir(), source: "startup" })).context, ["hello"]);
	assert.deepEqual((await run({ hook_event_name: "UserPromptSubmit", session_id: "s", cwd: tmpdir(), prompt: "p" })).context, ["hello"]);
	assert.deepEqual((await run(tool("PreToolUse", "Bash", {}))).context, []);
});

test("a failing or hanging hook is an error and decides nothing", async () => {
	const root = await plugin(
		{ PreToolUse: [{ hooks: [cmd("fail.sh"), cmd("hang.sh", 1)] }] },
		{ "fail.sh": `echo broken >&2; exit 1`, "hang.sh": `sleep 30` },
	);
	const out = await (await loadHooks(root))(tool("PreToolUse", "Bash", {}));
	assert.equal(out.refusal, undefined);
	assert.equal(out.errors.length, 2);
	assert.match(out.errors[0], /fail\.sh.*exit 1: broken/);
	assert.match(out.errors[1], /hang\.sh.*timed out after 1s/);
});

test("SessionStart hooks export variables through CLAUDE_ENV_FILE", async () => {
	const root = await plugin(
		{ SessionStart: [{ hooks: [cmd("env.sh")] }] },
		{ "env.sh": `printf 'export HOOK_TEST_A=one HOOK_TEST_B=%q\\n' "two words" >>"$CLAUDE_ENV_FILE"` },
	);
	const out = await (await loadHooks(root))({ hook_event_name: "SessionStart", session_id: "s", cwd: tmpdir(), source: "startup" });
	assert.deepEqual(out.errors, []);
	assert.deepEqual(out.env, { HOOK_TEST_A: "one", HOOK_TEST_B: "two words" });
});

test("a CLAUDE_ENV_FILE that cannot be read is an error, not an empty export", { skip: process.getuid?.() === 0 && "root reads a mode-000 file" }, async () => {
	const root = await plugin(
		{ SessionStart: [{ hooks: [cmd("env.sh")] }] },
		{ "env.sh": `echo 'export HOOK_TEST_A=one' >>"$CLAUDE_ENV_FILE"; chmod 000 "$CLAUDE_ENV_FILE"` },
	);
	const out = await (await loadHooks(root))({ hook_event_name: "SessionStart", session_id: "s", cwd: tmpdir(), source: "startup" });
	assert.deepEqual(out.env, {});
	assert.equal(out.errors.length, 1);
	assert.match(out.errors[0], /CLAUDE_ENV_FILE/);
});

test("a matcher that is not a valid regex is an error, and the other groups still run", async () => {
	const root = await plugin(
		{ PreToolUse: [{ matcher: "Bash(", hooks: [cmd("no.sh")] }, { matcher: "Bash", hooks: [cmd("no.sh")] }] },
		{ "no.sh": `echo refused >&2; exit 2` },
	);
	const out = await (await loadHooks(root))(tool("PreToolUse", "Bash", {}));
	assert.equal(out.refusal, "refused");
	assert.equal(out.errors.length, 1);
	assert.match(out.errors[0], /Bash\(/);
});

test("hooks.json that cannot be read rejects", async () => {
	await assert.rejects(loadHooks(join(tmpdir(), "no-such-plugin")), /hooks\.json/);
});

test("this plugin's hooks refuse a push with --no-verify and point git at the review gate", async () => {
	const root = resolve(here, "..");
	const run = await loadHooks(root);
	const out = await run(tool("PreToolUse", "Bash", { command: "git push --no-verify" }));
	assert.match(out.refusal ?? "", /No --no-verify on a push/);
	assert.equal((await run(tool("PreToolUse", "Bash", { command: "git push" }))).refusal, undefined);

	// git-hooks-path.sh adds its entry after any already in the environment.
	const n = Number(process.env.GIT_CONFIG_COUNT ?? 0);
	const start = await run({ hook_event_name: "SessionStart", session_id: "s", cwd: tmpdir(), source: "startup" });
	assert.equal(start.env[`GIT_CONFIG_KEY_${n}`], "core.hooksPath");
	assert.equal(start.env[`GIT_CONFIG_VALUE_${n}`], join(root, "hooks", "git"));
	assert.ok(await readFile(join(root, "hooks", "git", "pre-push")));
});
