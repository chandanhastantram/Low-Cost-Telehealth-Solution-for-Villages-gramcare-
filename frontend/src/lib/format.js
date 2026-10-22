const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" });
const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const fullFmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export const fmtDay = (d) => dayFmt.format(new Date(d));
export const fmtTime = (d) => timeFmt.format(new Date(d));
export const fmtFull = (d) => fullFmt.format(new Date(d));

export function isToday(d) {
  return new Date(d).toDateString() === new Date().toDateString();
}

/** "in 2h 15m", "in 3 days", "20 min ago" */
export function relative(d, now = Date.now()) {
  const diff = new Date(d).getTime() - now;
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  let text;
  if (mins < 1) text = "now";
  else if (mins < 60) text = `${mins} min`;
  else if (mins < 60 * 24) text = `${Math.floor(mins / 60)}h ${mins % 60}m`;
  else text = `${Math.round(mins / 1440)} day${Math.round(mins / 1440) === 1 ? "" : "s"}`;
  if (text === "now") return "right now";
  return diff > 0 ? `in ${text}` : `${text} ago`;
}

export const MODE_LABEL = {
  live_audio: "Audio call",
  live_video: "Video call",
  store_forward: "Store & forward",
};
