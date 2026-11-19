/**
 * The agent-estate plugin's hooks (../hooks/hooks.json) in pi: the pi extension
 * that the repo's package.json loads. It turns pi's events into Claude Code's
 * hook events, runs the hooks with ./claude-hooks.ts, and carries what they
 * decide back into pi:
 *
 *   Claude Code event          pi event                  outcome in pi
 *   SessionStart startup       session_start startup     context: a hidden message in the session;
 *   SessionStart resume        session_start resume|fork   exported env set for the agent's bash
 *   SessionStart clear         session_start new
 *   SessionStart compact       session_compact
 *   UserPromptSubmit           input                     refusal drops the prompt; context as above
 *   PreToolUse                 tool_call                 refusal blocks the call; context joins its result
 *   PostToolUse                tool_result, unless the   context appended to the result
 *                                call failed
 *
 * pi's bash, read, write and edit tools go to the hooks as Bash, Read, Write and
 * Edit with Claude Code's input fields; other tools keep their pi name and input.
 *
 * Variables a SessionStart hook exports reach the agent's bash commands only, as
 * in Claude Code: not the user's own `!` commands, nor the hooks. To that end the
 * extension replaces pi's bash tool with the same tool plus those variables.
 *
 * The pi process's environment carries CLAUDE_PLUGIN_ROOT, so the skills'
 * `${CLAUDE_PLUGIN_ROOT}/hooks/...` commands run as written, and CLAUDE_PID set
 * to this pi process, which context-handover.sh keys a handover on.
 */
import { writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createBashToolDefinition, type ExtensionAPI, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { type HookInput, type HookOutcome, loadHooks } from "./claude-hooks.ts";

const pluginRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const CLAUDE_TOOL_NAMES: Record<string, string> = { bash: "Bash", read: "Read", write: "Write", edit: "Edit" };

export default async function (pi: ExtensionAPI) {
	const runHooks = await loadHooks(pluginRoot);
	process.env.CLAUDE_PLUGIN_ROOT = pluginRoot;
	process.env.CLAUDE_PID = String(process.pid);

	// What SessionStart hooks exported, latest value per name, for the agent's bash.
	const sessionExports: Record<string, string> = {};
	// PreToolUse context by tool call id, held until that call's result exists to carry it.
	const preToolContext = new Map<string, string[]>();
	// True once the user was told the context size cannot be written.
	let tokenFileFailed = false;

	const bash = createBashToolDefinition(process.cwd());
	pi.registerTool({
		...bash,
		// Built per call, as pi builds its own from the shell settings in force.
		execute: (id, params, signal, onUpdate, ctx) => {
			const settings = pi.getSettings();
			return createBashToolDefinition(ctx.cwd, {
				shellPath: settings.shellPath && expandTilde(settings.shellPath),
				commandPrefix: settings.shellCommandPrefix,
				spawnHook: (spawn) => ({ ...spawn, env: { ...spawn.env, ...sessionExports } }),
			}).execute(id, params, signal, onUpdate, ctx);
		},
	});

	async function run(ctx: ExtensionContext, input: Omit<HookInput, "session_id" | "transcript_path" | "cwd">): Promise<HookOutcome> {
		const outcome = await runHooks({
			session_id: ctx.sessionManager.getSessionId(),
			transcript_path: ctx.sessionManager.getSessionFile(),
			cwd: ctx.cwd,
			...input,
		});
		Object.assign(sessionExports, outcome.env);
		if (outcome.errors.length > 0 && ctx.hasUI) ctx.ui.notify(`agent-estate hooks:\n${outcome.errors.join("\n")}`, "warning");
		return outcome;
	}

	// Into the session at once when pi is idle, at the end of the turn otherwise;
	// the model reads it on its next request either way, and it survives a reload.
	function addContext(context: string[]): void {
		if (context.length === 0) return;
		pi.sendMessage({ customType: "agent-estate-hooks", content: context.join("\n\n"), display: false });
	}

	// context-handover.sh's nudge reads the context size from the file Claude
	// Code's status line writes (its header); in pi this is that writer.
	async function publishContextTokens(ctx: ExtensionContext): Promise<void> {
		const tokens = ctx.getContextUsage()?.tokens;
		if (tokens == null) return;
		const file = `${process.env.XDG_RUNTIME_DIR || "/tmp"}/claude-context-tokens-${ctx.sessionManager.getSessionId()}`;
		try {
			await writeFile(file, `${tokens}\n`);
		} catch (e) {
			if (tokenFileFailed || !ctx.hasUI) return;
			tokenFileFailed = true;
			ctx.ui.notify(`agent-estate: writing ${file}: ${(e as Error).message}; no handover reminders this session`, "warning");
		}
	}

	pi.on("session_start", async (event, ctx) => {
		// A reload replaces this extension, not the session: its start already ran.
		if (event.reason === "reload") return;
		const source = event.reason === "new" ? "clear" : event.reason === "startup" ? "startup" : "resume";
		addContext((await run(ctx, { hook_event_name: "SessionStart", source })).context);
	});

	pi.on("session_compact", async (_event, ctx) => {
		addContext((await run(ctx, { hook_event_name: "SessionStart", source: "compact" })).context);
	});

	pi.on("input", async (event, ctx) => {
		await publishContextTokens(ctx);
		const outcome = await run(ctx, { hook_event_name: "UserPromptSubmit", prompt: event.text });
		if (outcome.refusal !== undefined) {
			if (ctx.hasUI) ctx.ui.notify(`Prompt refused by a hook:\n${outcome.refusal}`, "error");
			return { action: "handled" };
		}
		addContext(outcome.context);
		return { action: "continue" };
	});

	pi.on("tool_call", async (event, ctx) => {
		const outcome = await run(ctx, { hook_event_name: "PreToolUse", ...claudeTool(event.toolName, event.input, ctx.cwd) });
		if (outcome.refusal !== undefined) return { block: true, reason: outcome.refusal };
		if (outcome.context.length > 0) preToolContext.set(event.toolCallId, outcome.context);
		return undefined;
	});

	pi.on("tool_result", async (event, ctx) => {
		await publishContextTokens(ctx);
		// Claude Code runs PostToolUse only after a tool succeeded.
		const post = event.isError ? [] : (await run(ctx, { hook_event_name: "PostToolUse", ...claudeTool(event.toolName, event.input, ctx.cwd) })).context;
		const notes = [...(preToolContext.get(event.toolCallId) ?? []), ...post];
		if (notes.length === 0) return undefined;
		return { content: [...event.content, { type: "text" as const, text: notes.join("\n\n") }], structuredContent: event.structuredContent };
	});

	// Every call that passed tool_call ends here, also those with no tool_result:
	// blocked by a later extension, or aborted.
	pi.on("tool_execution_end", async (event) => {
		preToolContext.delete(event.toolCallId);
	});
}

/** A pi tool call as Claude Code's hooks expect it: Claude Code's tool name, and an absolute file_path for Read, Write and Edit. */
function claudeTool(toolName: string, input: Record<string, unknown>, cwd: string) {
	const onFile = ["read", "write", "edit"].includes(toolName) && typeof input.path === "string";
	return {
		tool_name: CLAUDE_TOOL_NAMES[toolName] ?? toolName,
		tool_input: onFile ? { ...input, file_path: toolPath(input.path as string, cwd) } : input,
	};
}

/**
 * The absolute file a pi file tool's path argument names, by pi's rules
 * (resolveToCwd in pi-coding-agent's dist/core/tools/path-utils.js, not
 * exported): unicode spaces read as plain ones, a leading `@` is dropped, `~`
 * is the home directory, and a relative path is relative to cwd.
 */
function toolPath(path: string, cwd: string): string {
	const plain = path.replace(/[  -   　]/g, " ");
	return resolve(cwd, expandTilde(plain.startsWith("@") ? plain.slice(1) : plain));
}

/** path with a leading `~` or `~/` read as the home directory; any other path unchanged. */
function expandTilde(path: string): string {
	if (path === "~") return homedir();
	return path.startsWith("~/") ? join(homedir(), path.slice(2)) : path;
}
