function nextCounts(previous, now) {
  // Taipei is UTC+8 throughout the year. Compute Monday on the local calendar.
  const local = new Date(now.getTime() + 8 * 3600000);
  const day = local.toISOString().slice(0, 10);
  local.setUTCDate(local.getUTCDate() - (local.getUTCDay() + 6) % 7);
  const keys = {day: day, week: local.toISOString().slice(0, 10), month: day.slice(0, 7)};
  const counts = {total: previous ? previous.counts.total + 1 : 1};
  for (const period of Object.keys(keys)) {
    counts[period] = previous && previous.keys[period] === keys[period] ? previous.counts[period] + 1 : 1;
  }
  return {keys, counts};
}

function doPost(e) {
  if (!e || !e.parameter || e.parameter.event !== 'v70-view') throw Error('Invalid event');
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const properties = PropertiesService.getScriptProperties();
    const key = 'v70.public.views';
    const next = nextCounts(JSON.parse(properties.getProperty(key)), new Date());
    properties.setProperty(key, JSON.stringify(next));
    return ContentService.createTextOutput(JSON.stringify(next.counts)).setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}