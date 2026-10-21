export async function getState(signal) {
  const response = await fetch("/api/state", { signal })
  if (!response.ok) throw new Error("NightOwl didn't answer.")
  return response.json()
}

export async function apply(partial) {
  const response = await fetch("/api/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(partial),
  })
  if (!response.ok) throw new Error("That change didn't land.")
  return response.json()
}

export async function applyPreset(id) {
  const response = await fetch("/api/preset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  })
  if (!response.ok) throw new Error("That preset isn't available.")
  return response.json()
}

export async function reconnect() {
  const response = await fetch("/api/reconnect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  })
  if (!response.ok) throw new Error("The monitor still isn't answering.")
  return response.json()
}

export async function windowAction(action) {
  await fetch("/api/window", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  })
}

export function subscribe(onState) {
  const source = new EventSource("/api/events")
  source.onmessage = (event) => {
    try {
      onState(JSON.parse(event.data))
    } catch {
      /* comment frames are not state */
    }
  }
  return source
}
