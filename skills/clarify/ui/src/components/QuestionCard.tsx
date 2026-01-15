import { Controller, type Control } from 'react-hook-form'
import clsx from 'clsx'
import type { ClarifyQuestion } from '../types'
import styles from './QuestionCard.module.css'

export type QuestionCardProps = {
  question: ClarifyQuestion
  control: Control<Record<string, any>>
  disabled?: boolean
}

const QuestionCard = ({ question, control, disabled }: QuestionCardProps) => {
  const showArtifacts = (question.artifact_paths ?? []).length > 0
  const showVisuals = (question.visual_assets ?? []).length > 0

  const renderInput = () => {
    switch (question.kind) {
      case 'single-choice':
        return (
          <Controller
            name={`${question.id}.selected`}
            control={control}
            rules={{ required: question.required !== false }}
            render={({ field }) => (
              <div className={styles.optionGroup}>
                {question.options.map((opt) => (
                  <label key={opt.id} className={styles.optionItem}>
                    <input
                      type="radio"
                      value={opt.id}
                      checked={field.value === opt.id}
                      onChange={(e) => field.onChange(e.target.value)}
                      disabled={disabled}
                    />
                    <span>
                      <strong>{opt.label}</strong>
                      {opt.description && (
                        <span className={styles.optionDescription}>{opt.description}</span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            )}
          />
        )
      case 'multi-choice':
        return (
          <Controller
            name={`${question.id}.selected`}
            control={control}
            render={({ field }) => (
              <div className={styles.optionGroup}>
                {question.options.map((opt) => {
                  const values: string[] = Array.isArray(field.value) ? field.value : []
                  const checked = values.includes(opt.id)
                  return (
                    <label key={opt.id} className={styles.optionItem}>
                      <input
                        type="checkbox"
                        value={opt.id}
                        checked={checked}
                        onChange={(e) => {
                          if (e.target.checked) {
                            field.onChange([...values, opt.id])
                          } else {
                            field.onChange(values.filter((v) => v !== opt.id))
                          }
                        }}
                        disabled={disabled}
                      />
                      <span>
                        <strong>{opt.label}</strong>
                        {opt.description && (
                          <span className={styles.optionDescription}>{opt.description}</span>
                        )}
                      </span>
                    </label>
                  )
                })}
              </div>
            )}
          />
        )
      case 'textarea':
        return (
          <Controller
            name={`${question.id}.value`}
            control={control}
            rules={{ required: question.required !== false }}
            render={({ field }) => (
              <textarea
                className={styles.textArea}
                rows={4}
                {...field}
                disabled={disabled}
                placeholder="Type your response"
              />
            )}
          />
        )
      case 'text':
      default:
        return (
          <Controller
            name={`${question.id}.value`}
            control={control}
            rules={{ required: question.required !== false }}
            render={({ field }) => (
              <input
                type="text"
                className={styles.textInput}
                {...field}
                disabled={disabled}
                placeholder="Type your response"
              />
            )}
          />
        )
    }
  }

  return (
    <section className={styles.card} aria-labelledby={`prompt-${question.id}`}>
      <div className={styles.header}>
        <div>
          <p id={`prompt-${question.id}`} className={styles.prompt}>
            {question.prompt}
          </p>
          {question.docs_link && (
            <a href={question.docs_link} target="_blank" rel="noreferrer" className={styles.docsLink}>
              View docs ↗
            </a>
          )}
        </div>
        {question.required !== false && <span className={styles.badge}>Required</span>}
      </div>
      <div className={styles.input}>{renderInput()}</div>
      <Controller
        name={`${question.id}.note`}
        control={control}
        render={({ field }) => (
          <textarea
            className={clsx(styles.textArea, styles.noteArea)}
            rows={2}
            placeholder="Optional notes"
            {...field}
            disabled={disabled}
          />
        )}
      />
      {(showArtifacts || showVisuals) && (
        <div className={styles.metaGrid}>
          {showArtifacts && (
            <div>
              <p className={styles.metaHeading}>Artifacts</p>
              <ul>
                {question.artifact_paths!.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {showVisuals && (
            <div>
              <p className={styles.metaHeading}>Visuals</p>
              <ul>
                {question.visual_assets!.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

export default QuestionCard
