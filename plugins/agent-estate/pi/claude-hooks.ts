/**
 * Runs a Claude Code plugin's hooks, as its `hooks/hooks.json` declares them, the
 * way Claude Code would, so that a harness other than Claude Code can host the
 * same hook scripts unchanged. The contract followed is
 * https://code.claude.com/docs/en/hooks for the four events hooks.json here uses.
 *
 * What the caller still owns: deciding when each event happens, and carrying
 * the outcome back into its own harness (refusing the tool call, adding the
 * context to the model's next request, exporting the environment).
 */
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

export type HookEventName = "SessionStart" | "UserPromptSubmit" | "PreToolUse" | "PostToolUse";

/** The JSON a hook command reads on stdin. */
export interface HookInput {
	hook_event_name: HookEventName;
	session_id: string;
	/** The session's transcript file; absent while the session has none. */
	transcript_path?: string;
	/** Absolute; the hook command also runs in it. */
	cwd: string;
	/** SessionStart only: what started the session. */
	source?: "startup" | "resume" | "clear" | "compact";
	/** UserPromptSubmit only: the user's prompt. */
	prompt?: string;
	/** PreToolUse and PostToolUse only: Claude Code's name for the tool (`Bash`, `Read`, ...). */
	tool_name?: string;
	/** PreToolUse and PostToolUse only, in Claude Code's shape: `command` for Bash, an absolute `file_path` for Read, Write and Edit. */
	tool_input?: Record<string, unknown>;
}

/** What one event's hooks decided, all of them taken together. */
export interface HookOutcome {
	/** Set when a hook refused the tool call (PreToolUse) or the prompt (UserPromptSubmit): the reasons given, for the model or the user. Never set for the other events. */
	refusal?: string;
	/** Text for the model's context, one entry per hook that gave some, in hooks.json's order. */
	context: string[];
	/** One line per hook that failed (exit status other than 0 and 2, a timeout, or a command that would not start), for the user; a failed hook decides nothing. */
	errors: string[];
	/** SessionStart only: variables the hooks exported through CLAUDE_ENV_FILE, which the agent's later shell commands in the session must see (Claude Code gives them to its Bash tool alone). Empty otherwise. */
	env: Record<string, string>;
}

/** Runs every hook that hooks.json registers for input's event and matches it, concurrently, and resolves when all have finished. Never rejects. */
export type RunHooks = (input: HookInput) => Promise<HookOutcome>;

interface CommandHook {
	type: string;
	command: string;
	/** Seconds. */
	timeout?: number;
}

interface MatcherGroup {
	matcher?: string;
	hooks: CommandHook[];
}

// Claude Code's default for a command hook without a timeout.
const DEFAULT_TIMEOUT_SECONDS = 600;

/**
 * Reads pluginRoot/hooks/hooks.json and returns the function that runs its hooks.
 * Each command runs under bash in input.cwd, with the environment of this
 * process plus CLAUDE_PLUGIN_ROOT (pluginRoot), CLAUDE_PROJECT_DIR (input.cwd)
 * and, for SessionStart, CLAUDE_ENV_FILE.
 *
 * Rejects when hooks.json cannot be read or is not JSON.
 */
export async function loadHooks(pluginRoot: string): Promise<RunHooks> {
	const path = join(pluginRoot, "hooks", "hooks.json");
	let events: Record<string, MatcherGroup[]>;
	try {
		events = JSON.parse(await readFile(path, "utf8")).hooks ?? {};
	} catch (e) {
		throw new Error(`reading ${path}: ${(e as Error).message}`);
	}

	return async (input) => {
		const outcome: HookOutcome = { context: [], errors: [], env: {} };
		const target = input.hook_event_name === "SessionStart" ? input.source : input.tool_name;
		const hooks = (events[input.hook_event_name] ?? [])
			.filter((g) => {
				try {
					return matches(g.matcher, target);
				} catch (e) {
					outcome.errors.push(`${input.hook_event_name} matcher ${JSON.stringify(g.matcher)}: ${(e as Error).message}`);
					return false;
				}
			})
			.flatMap((g) => g.hooks.filter((h) => h.type === "command"));
		if (hooks.length === 0) return outcome;

		const env: NodeJS.ProcessEnv = { ...process.env, CLAUDE_PLUGIN_ROOT: pluginRoot, CLAUDE_PROJECT_DIR: input.cwd };
		let envDir: string | undefined;
		try {
			if (input.hook_event_name === "SessionStart") {
				envDir = await mkdtemp(join(tmpdir(), "claude-hooks-"));
				env.CLAUDE_ENV_FILE = join(envDir, "env");
			}
			const runs = await Promise.all(hooks.map((h) => runCommand(h, input, env)));
			const refusals: string[] = [];
			runs.forEach((r, i) => judge(hooks[i].command, r, input.hook_event_name, outcome, refusals));
			if (refusals.length > 0) outcome.refusal = refusals.join("\n\n");
			if (env.CLAUDE_ENV_FILE) outcome.env = await exported(env.CLAUDE_ENV_FILE, env, outcome.errors);
		} catch (e) {
			outcome.errors.push(`hooks for ${input.hook_event_name}: ${(e as Error).message}`);
		} finally {
			if (envDir) await rm(envDir, { recursive: true, force: true }).catch(() => {});
		}
		return outcome;
	};
}

/**
 * Whether a hooks.json matcher selects target. Absent, empty and `*` select
 * everything; letters, digits, `_` and `|` alone are an exact name or a list of
 * them; anything else is a regular expression, which must match somewhere in
 * target. An undefined target (an event without one) matches every matcher.
 * Throws when matcher is neither and does not compile as a regular expression.
 */
function matches(matcher: string | undefined, target: string | undefined): boolean {
	if (!matcher || matcher === "*" || target === undefined) return true;
	if (/^[\w|]+$/.test(matcher)) return matcher.split("|").includes(target);
	return new RegExp(matcher).test(target);
}

interface CommandRun {
	/** null when the command did not exit by itself: killed at its timeout, or never started. */
	status: number | null;
	stdout: string;
	stderr: string;
	/** Why status is null. */
	failure?: string;
}

function runCommand(hook: CommandHook, input: HookInput, env: NodeJS.ProcessEnv): Promise<CommandRun> {
	return new Promise((resolve) => {
		// detached: its own process group, so a timeout kills what the hook started too.
		const child = spawn("bash", ["-c", hook.command], { cwd: input.cwd, env, detached: true, stdio: ["pipe", "pipe", "pipe"] });
		let stdout = "";
		let stderr = "";
		let failure: string | undefined;
		const seconds = hook.timeout ?? DEFAULT_TIMEOUT_SECONDS;
		const timer = setTimeout(() => {
			failure = `timed out after ${seconds}s`;
			try {
				process.kill(-child.pid!, "SIGKILL");
			} catch {
				child.kill("SIGKILL");
			}
		}, seconds * 1000);
		child.stdout.on("data", (d) => (stdout += d));
		child.stderr.on("data", (d) => (stderr += d));
		child.on("error", (e) => (failure ??= e.message));
		child.on("close", (status) => {
			clearTimeout(timer);
			resolve({ status: failure ? null : status, stdout, stderr, failure });
		});
		// A hook that exits without reading stdin closes the pipe under us.
		child.stdin.on("error", () => {});
		child.stdin.end(JSON.stringify(input));
	});
}

/** Adds what one hook's run decided to outcome and refusals, by Claude Code's rules for event. */
function judge(command: string, run: CommandRun, event: HookEventName, outcome: HookOutcome, refusals: string[]): void {
	const gates = event === "PreToolUse" || event === "UserPromptSubmit";
	if (run.status === 2) {
		const reason = run.stderr.trim();
		if (gates) refusals.push(reason || `refused by ${command}`);
		else if (event === "PostToolUse" && reason) outcome.context.push(reason);
		else if (reason) outcome.errors.push(`${command}: ${reason}`);
		return;
	}
	if (run.status !== 0) {
		const why = run.failure ?? `exit ${run.status}`;
		const detail = run.stderr.trim().split("\n")[0];
		outcome.errors.push(`${command}: ${why}${detail ? `: ${detail}` : ""}`);
		return;
	}

	const text = run.stdout.trim();
	if (!text) return;
	let output: any;
	if (text.startsWith("{")) {
		try {
			output = JSON.parse(text);
		} catch {
			// Not JSON after all: plain text, as below.
		}
	}
	if (output === undefined) {
		// Plain stdout reaches the model only for these two events.
		if (event === "SessionStart" || event === "UserPromptSubmit") outcome.context.push(text);
		return;
	}
	const specific = output.hookSpecificOutput ?? {};
	if (gates && specific.permissionDecision === "deny") refusals.push(specific.permissionDecisionReason || `refused by ${command}`);
	if (output.decision === "block") {
		if (gates) refusals.push(output.reason || `refused by ${command}`);
		else if (output.reason) outcome.context.push(output.reason);
	}
	if (typeof specific.additionalContext === "string" && specific.additionalContext) outcome.context.push(specific.additionalContext);
}

/**
 * The variables that sourcing envFile in bash sets or changes relative to env;
 * an empty record when the file is empty or missing. A failure is added to
 * errors and gives an empty record.
 */
async function exported(envFile: string, env: NodeJS.ProcessEnv, errors: string[]): Promise<Record<string, string>> {
	let text: string;
	try {
		text = await readFile(envFile, "utf8");
	} catch (e) {
		if ((e as NodeJS.ErrnoException).code === "ENOENT") return {};
		errors.push(`reading CLAUDE_ENV_FILE: ${(e as Error).message}`);
		return {};
	}
	if (!text.trim()) return {};
	const run = await runCommand(
		{ type: "command", command: `set -a; . "$CLAUDE_ENV_FILE" && env -0`, timeout: 10 },
		{ hook_event_name: "SessionStart", session_id: "", cwd: tmpdir() },
		env,
	);
	if (run.status !== 0) {
		errors.push(`sourcing CLAUDE_ENV_FILE: ${run.failure ?? `exit ${run.status}`}: ${run.stderr.trim()}`);
		return {};
	}
	const changed: Record<string, string> = {};
	for (const entry of run.stdout.split("\0")) {
		const eq = entry.indexOf("=");
		if (eq <= 0) continue;
		const [name, value] = [entry.slice(0, eq), entry.slice(eq + 1)];
		// bash's own bookkeeping, and the variables this module set for the hooks.
		if (["_", "SHLVL", "PWD", "OLDPWD", "CLAUDE_ENV_FILE", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR"].includes(name)) continue;
		if (env[name] !== value) changed[name] = value;
	}
	return changed;
}
