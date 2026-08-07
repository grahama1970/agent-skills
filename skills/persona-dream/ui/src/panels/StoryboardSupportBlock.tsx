/**
 * StoryboardSupportBlock, extracted from DreamWorkspace.tsx.
 */
import { nvis } from '../styles'


export function StoryboardSupportBlock({ title, body, items }: { title: string; body: string; items: string[] }) {
  return (
    <div style={nvis.storyboardSupportBlock}>
      <div style={nvis.storyboardSupportTitle}>{title}</div>
      <p style={nvis.storyboardSupportBody}>{body}</p>
      {items.length > 0 && (
        <ul style={nvis.storyboardSupportList}>
          {items.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
