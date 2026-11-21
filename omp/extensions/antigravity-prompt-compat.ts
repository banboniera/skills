// Google's Antigravity backend answers some omp prompt phrases with a false 429 RESOURCE_EXHAUSTED
// (oh-my-pi #19333, #19609). Each rewrite below was bisected from the real prompt and verified.
// ACP transports skip before_provider_request, so this runs per turn: a mid-turn fallback to
// another provider keeps the (meaning-equivalent) reworded prompt.
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

const REWRITES: Array<[string, string]> = [
	["You are omp's trusted coding assistant.", "You are omp's coding assistant."],
	[
		"Read xd://<tool> for full docs + JSON schema before first use.",
		"Before using a device, read its full documentation and JSON schema at its xd:// address.",
	],
	["to xd://<tool> via", "to xd://<name> via"],
	[
		": it selects only the lines you and your subagents wrote and never touches other agents' staged or unstaged work.",
		": it commits only this session's own edits.",
	],
	["`…`, `..`, collapsed", "elision markers (ellipsis or two dots), collapsed"],
];

export default function antigravityPromptCompat(omp: ExtensionAPI) {
	omp.on("before_agent_start", (event, ctx) => {
		if (ctx.model?.provider !== "antigravity-cli") return;
		const systemPrompt = event.systemPrompt.map(text =>
			REWRITES.reduce((out, [from, to]) => out.replaceAll(from, to), text),
		);
		if (systemPrompt.every((text, i) => text === event.systemPrompt[i])) return;
		return { systemPrompt };
	});
}
