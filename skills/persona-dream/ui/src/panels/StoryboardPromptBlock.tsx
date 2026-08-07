/**
 * StoryboardPromptBlock, extracted from DreamWorkspace.tsx.
 */
import { acceptedStoryboardFrame, panelHasAcceptedStoryboardFrames, storyboardPanelPromptText, storyboardRecord, storyboardShotCode, storyboardStringList, storyboardTargetPanelIds } from '../lib/storyboard'
import { nvis } from '../styles'

export function StoryboardPromptBlock({ prompt }: { prompt: Record<string, unknown> }) {
  const panelPrompt = String(prompt.panel_prompt ?? 'Missing storyboard panel generation prompt')
  const startPrompt = String(prompt.start_frame_prompt ?? 'Missing start-frame prompt')
  const endPrompt = String(prompt.end_frame_prompt ?? 'Missing end-frame prompt')
  const requirements = storyboardStringList(prompt.reference_requirements)
  const negativePrompt = String(prompt.negative_prompt ?? 'Missing negative prompt')
  return (
    <div style={nvis.storyboardPromptBlock}>
      <div style={nvis.storyboardPromptHeader}>Panel Generation Prompt</div>
      <p style={nvis.storyboardPromptText}>{panelPrompt}</p>
      <div style={nvis.storyboardPromptPair}>
        <div>
          <span style={nvis.storyboardPromptLabel}>Start</span>
          <p>{startPrompt}</p>
        </div>
        <div>
          <span style={nvis.storyboardPromptLabel}>End</span>
          <p>{endPrompt}</p>
        </div>
      </div>
      {requirements.length > 0 && (
        <div style={nvis.storyboardPromptRequirements}>
          {requirements.map((item) => <span key={item}>{item}</span>)}
        </div>
      )}
      <div style={nvis.storyboardNegativePrompt}>Must not: {negativePrompt}</div>
    </div>
  )
}
