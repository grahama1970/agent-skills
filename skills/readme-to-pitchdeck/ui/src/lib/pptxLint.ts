// Phase 4 (Gemini spec): advisory presentation-quality lint, mirroring the
// PPTX builder's sizing heuristics (body font drops below the 12pt floor
// beyond these bounds — see references/pptx_visual_rules.md). These warnings
// complement, never replace, the server-side fail-closed claim gates.

import type { UiSlide } from '../types'

export interface LintWarning {
  elementId: string
  type: 'MAX_BULLETS_EXCEEDED' | 'LINE_LENGTH' | 'TITLE_LENGTH' | 'ELEMENT_TEXT_DENSITY'
  message: string
}

const MAX_RECOMMENDED_BULLETS = 5
const MAX_CHARACTERS_PER_BULLET = 110
const MAX_TITLE_CHARACTERS = 60

export function lintSlide(slide: UiSlide): LintWarning[] {
  const warnings: LintWarning[] = []
  if (slide.body.length > MAX_RECOMMENDED_BULLETS) {
    warnings.push({
      elementId: slide.id,
      type: 'MAX_BULLETS_EXCEEDED',
      message: `${slide.body.length} bullets (recommended max ${MAX_RECOMMENDED_BULLETS}); PPTX body text will shrink below comfortable size.`,
    })
  }
  slide.body.forEach((bullet, index) => {
    if (bullet.length > MAX_CHARACTERS_PER_BULLET) {
      warnings.push({
        elementId: `${slide.id}-b${index}`,
        type: 'LINE_LENGTH',
        message: `Bullet ${index + 1} is ${bullet.length} chars (recommended max ${MAX_CHARACTERS_PER_BULLET}).`,
      })
    }
  })
  if (slide.title.length > MAX_TITLE_CHARACTERS) {
    warnings.push({
      elementId: `${slide.id}-title`,
      type: 'TITLE_LENGTH',
      message: `Title is ${slide.title.length} chars (recommended max ${MAX_TITLE_CHARACTERS}); may wrap in the PPTX title box.`,
    })
  }
  for (const element of slide.elements) {
    if (element.type === 'text' && element.text) {
      const areaChars = element.w * element.h * 4600 // rough capacity at ~20pt on the 16:9 canvas
      if (element.text.length > areaChars) {
        warnings.push({
          elementId: `${slide.id}-${element.id}`,
          type: 'ELEMENT_TEXT_DENSITY',
          message: `Element '${element.id}' likely overflows its box (${element.text.length} chars in a ${Math.round(element.w * 100)}×${Math.round(element.h * 100)}% frame).`,
        })
      }
    }
  }
  return warnings
}
