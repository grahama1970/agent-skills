/** Lane label column width — matches battle-004-shell mockup --label-w */
export const BATTLE_LANE_LABEL_PX = 380;

/** Mockup shell proportions from battle-004-original-mockup.png / shell HTML */
export const BATTLE_MOCKUP_VIEWPORT = { width: 1672, height: 941 } as const;
export const BATTLE_MOCKUP_LEFT_RAIL_PX = 260;
export const BATTLE_MOCKUP_AGENT_PANE_PX = 360;
/** Minimum topbar height; live-events column grows shell like HTML mockup (~162px). */
export const BATTLE_MOCKUP_HEADER_MIN_PX = 118;
/** @deprecated Use auto grid row + BATTLE_MOCKUP_HEADER_MIN_PX. Kept for region regression slack. */
export const BATTLE_MOCKUP_HEADER_PX = 118;
export const BATTLE_MOCKUP_LEGEND_PX = 34;
export const BATTLE_MOCKUP_FOOTER_PX = 64;
export const BATTLE_MOCKUP_LANE_ROW_ROOT_PX = 92;
export const BATTLE_MOCKUP_LANE_ROW_CHILD_PX = 86;
