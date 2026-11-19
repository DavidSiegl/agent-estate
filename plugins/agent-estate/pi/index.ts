/**
 * The agent-estate plugin's hooks (../hooks/hooks.json) in pi: the pi extension
 * that the repo's package.json loads. It turns pi's events into Claude Code's
 * hook events, runs the hooks with ./claude-hooks.ts, and carries what they
 * decide back into pi:
 *
 *   Claude Code event          pi event                  outcome in pi
 *   SessionStart startup       session_start startup     context for the next model run;
 *   SessionStart resume        session_start resume|fork   exported env set for every bash call
 *   SessionStart clear         session_start new
 *   SessionStart compact       session_compact
 *   UserPromptSubmit           input                     refusal drops the prompt; context as above
 *   PreToolUse                 tool_call                 refusal blocks the call; context joins its result
 *   PostToolUse                tool_result               context appended to the result
 *
 * pi's bash, read, write and edit tools go to the hooks as Bash, Read, Write and
 * Edit with Claude Code's input fields; other tools keep their pi name and input.
 *
 * Every bash command of the session also sees CLAUDE_PLUGIN_ROOT, so the skills'
 * `${CLAUDE_PLUGIN_ROOT}/hooks/...` commands run as written, and CLAUDE_PID set to
 * this pi process, which context-handover.sh keys a handover on.
 */
import { writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { type HookInput, type HookOutcome, loadHooks } from "./claude-hooks.ts";

const pluginRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const CLAUDE_TOOL_NAMES: Record<string, string> = { bash: "Bash", read: "Read", write: "Write", edit: "Edit" };

export default async function (pi: ExtensionAPI) {
	const runHooks = await loadHooks(pluginRoot);
	// Hook context not yet shown to the model; before_agent_start sends it.
	let pending: string[] = [];
	// PreToolUse context by tool call id, held until that call's result exists to carry it.
	const preToolContext = new Map<string, string[]>();

	async function run(ctx: ExtensionContext, input: Omit<HookInput, "session_id" | "transcript_path" | "cwd">): Promise<HookOutcome> {
		const outcome = await runHooks({
			session_id: ctx.sessionManager.getSessionId(),
			transcript_path: ctx.sessionManager.getSessionFile(),
			cwd: ctx.cwd,
			...input,
		});
		Object.assign(process.env, outcome.env);
		if (outcome.errors.length > 0 && ctx.hasUI) ctx.ui.notify(`agent-estate hooks:\n${outcome.errors.join("\n")}`, "warning");
		return outcome;
	}

	// context-handover.sh's nudge reads the context size from the file Claude
	// Code's status line writes (its header); in pi this is that writer.
	async function publishContextTokens(ctx: ExtensionContext): Promise<void> {
		const tokens = ctx.getContextUsage()?.tokens;
		if (tokens == null) return;
		const file = `${process.env.XDG_RUNTIME_DIR || "/tmp"}/claude-context-tokens-${ctx.sessionManager.getSessionId()}`;
		await writeFile(file, `${tokens}\n`).catch(() => {});
	}

	function claudeTool(toolName: string, input: Record<string, unknown>, cwd: string) {
		const onFile = ["read", "write", "edit"].includes(toolName) && typeof input.path === "string";
		return {
			tool_name: CLAUDE_TOOL_NAMES[toolName] ?? toolName,
			tool_input: onFile ? { ...input, file_path: resolve(cwd, input.path as string) } : input,
		};
	}

	pi.on("session_start", async (event, ctx) => {
		process.env.CLAUDE_PLUGIN_ROOT = pluginRoot;
		process.env.CLAUDE_PID = String(process.pid);
		// A reload replaces this extension, not the session: its start already ran.
		if (event.reason === "reload") return;
		const source = event.reason === "new" ? "clear" : event.reason === "startup" ? "startup" : "resume";
		pending.push(...(await run(ctx, { hook_event_name: "SessionStart", source })).context);
	});

	pi.on("session_compact", async (_event, ctx) => {
		pending.push(...(await run(ctx, { hook_event_name: "SessionStart", source: "compact" })).context);
	});

	pi.on("input", async (event, ctx) => {
		await publishContextTokens(ctx);
		const outcome = await run(ctx, { hook_event_name: "UserPromptSubmit", prompt: event.text });
		if (outcome.refusal !== undefined) {
			if (ctx.hasUI) ctx.ui.notify(`Prompt refused by a hook:\n${outcome.refusal}`, "error");
			return { action: "handled" };
		}
		pending.push(...outcome.context);
		return { action: "continue" };
	});

	pi.on("before_agent_start", async () => {
		if (pending.length === 0) return undefined;
		const content = pending.join("\n\n");
		pending = [];
		return { message: { customType: "agent-estate-hooks", content, display: false } };
	});

	pi.on("tool_call", async (event, ctx) => {
		const outcome = await run(ctx, { hook_event_name: "PreToolUse", ...claudeTool(event.toolName, event.input, ctx.cwd) });
		if (outcome.refusal !== undefined) return { block: true, reason: outcome.refusal };
		if (outcome.context.length > 0) preToolContext.set(event.toolCallId, outcome.context);
		return undefined;
	});

	pi.on("tool_result", async (event, ctx) => {
		await publishContextTokens(ctx);
		const outcome = await run(ctx, { hook_event_name: "PostToolUse", ...claudeTool(event.toolName, event.input, ctx.cwd) });
		const notes = [...(preToolContext.get(event.toolCallId) ?? []), ...outcome.context];
		preToolContext.delete(event.toolCallId);
		if (notes.length === 0) return undefined;
		return { content: [...event.content, { type: "text" as const, text: notes.join("\n\n") }], structuredContent: event.structuredContent };
	});
}
