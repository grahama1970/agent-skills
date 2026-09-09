export function LiteralControls() {
  return (
    <form data-qid="settings:form:profile" data-qs-action="SETTINGS_SAVE_PROFILE" title="Profile settings">
      <input
        data-qid="settings:input:name"
        data-qs-action="SETTINGS_SET_NAME"
        title="Name"
        onChange={() => {}}
      />
      <button
        data-qid="settings:action:save"
        data-qs-action="SETTINGS_SAVE"
        title="Save settings"
        onClick={() => {}}
      >
        Save
      </button>
    </form>
  )
}
