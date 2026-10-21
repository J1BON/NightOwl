import { useCallback, useEffect, useRef, useState } from "react"
import { apply, applyPreset, getState, reconnect, subscribe, windowAction } from "./api.js"

const shellHint = new URLSearchParams(window.location.search).has("shell")

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function marksFor(max) {
  if (!max) return [0]
  const marks = [0, 0.25, 0.5, 0.75, 1].map((part) => Math.round(max * part))
  return [...new Set(marks)]
}

export default function App() {
  const [state, setState] = useState(null)
  const [draft, setDraft] = useState("")
  const [loadError, setLoadError] = useState("")
  const stateRef = useRef(null)
  const dragging = useRef(new Set())
  const inflight = useRef(0)
  const missed = useRef(false)
  const editing = useRef(false)
  const lastSeq = useRef(0)
  const pending = useRef({})
  const timer = useRef(0)
  const heroRef = useRef(null)
  const releaseTimers = useRef({})

  const hold = (key) => {
    dragging.current.add(key)
    window.clearTimeout(releaseTimers.current[key])
    releaseTimers.current[key] = window.setTimeout(() => {
      dragging.current.delete(key)
      if (!dragging.current.size && !editing.current && missed.current && inflight.current === 0) {
        missed.current = false
        getState().then(accept).catch(() => {})
      }
    }, 600)
  }

  const accept = useCallback((next) => {
    if (!next || typeof next.seq !== "number") return
    if (next.seq < lastSeq.current) return
    lastSeq.current = next.seq
    if (inflight.current || dragging.current.size || editing.current) {
      missed.current = true
      return
    }
    stateRef.current = next
    setState(next)
    setDraft(String(next.brightness))
  }, [])

  const mergeServer = useCallback((next) => {
    if (!next) return
    lastSeq.current = Math.max(lastSeq.current, next.seq || 0)
    setState((prev) => {
      const base = prev ?? next
      const merged = { ...next }
      if (dragging.current.has("brightness")) merged.brightness = base.brightness
      if (dragging.current.has("contrast")) merged.contrast = base.contrast
      if (dragging.current.has("veil")) merged.veil = base.veil
      if (dragging.current.has("warmth")) merged.warmth = base.warmth
      stateRef.current = merged
      return merged
    })
    if (!editing.current && !dragging.current.has("brightness")) {
      setDraft(String(next.brightness))
    }
  }, [])

  const flush = useCallback(() => {
    window.clearTimeout(timer.current)
    const body = pending.current
    pending.current = {}
    if (!Object.keys(body).length) return
    inflight.current += 1
    apply(body)
      .then((next) => mergeServer(next))
      .catch(() => {
        missed.current = true
      })
      .finally(() => {
        inflight.current = Math.max(0, inflight.current - 1)
        if (inflight.current === 0 && missed.current && !dragging.current.size && !editing.current) {
          missed.current = false
          getState().then(accept).catch(() => {})
        }
      })
  }, [accept, mergeServer])

  const schedule = useCallback(
    (partial) => {
      pending.current = { ...pending.current, ...partial }
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(flush, 45)
    },
    [flush],
  )

  const patchLocal = useCallback((partial) => {
    const prev = stateRef.current
    if (!prev) return null
    const next = { ...prev, ...partial }
    const match = next.presets?.find(
      (preset) =>
        preset.brightness === next.brightness && preset.veil === next.veil && preset.warmth === next.warmth,
    )
    next.preset = match ? match.id : null
    stateRef.current = next
    setState(next)
    return next
  }, [])

  useEffect(() => {
    let poll = 0
    let source
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 5000)
    getState(controller.signal)
      .then((next) => {
        lastSeq.current = next.seq || 0
        stateRef.current = next
        setState(next)
        setDraft(String(next.brightness))
        setLoadError("")
      })
      .catch((error) => {
        if (error?.name === "AbortError") return
        setLoadError("NightOwl isn't running. Start it, then try again.")
      })
    source = subscribe(accept)
    source.onerror = () => {
      source.close()
      if (!poll) {
        poll = window.setInterval(() => {
          if (inflight.current || dragging.current.size || editing.current) return
          getState().then(accept).catch(() => {})
        }, 1200)
      }
    }
    return () => {
      window.clearTimeout(timeout)
      window.clearTimeout(timer.current)
      window.clearInterval(poll)
      controller.abort()
      source?.close()
    }
  }, [accept])

  useEffect(() => {
    let pendingDelta = 0
    const onWheel = (event) => {
      const range = event.target?.closest?.("input[type=range]")
      if (!range || !range.closest("main")) return
      event.preventDefault()
      if (range.id !== "brightness") return
      const current = stateRef.current
      if (!current || editing.current) return
      pendingDelta += event.deltaY
      const threshold = event.shiftKey ? 20 : 48
      if (Math.abs(pendingDelta) < threshold) return
      const direction = pendingDelta > 0 ? -1 : 1
      pendingDelta = 0
      const next = clamp(current.brightness + direction, 0, current.brightnessMax)
      patchLocal({ brightness: next })
      setDraft(String(next))
      schedule({ brightness: next })
    }
    window.addEventListener("wheel", onWheel, { capture: true, passive: false })
    return () => window.removeEventListener("wheel", onWheel, { capture: true })
  }, [patchLocal, schedule])

  const setBrightness = (value, immediate = false) => {
    const current = stateRef.current
    if (!current) return
    const next = clamp(value, 0, current.brightnessMax)
    hold("brightness")
    patchLocal({ brightness: next })
    if (!editing.current) setDraft(String(next))
    if (immediate) {
      pending.current = { ...pending.current, brightness: next }
      flush()
    } else {
      schedule({ brightness: next })
    }
  }

  const engage = (key, active) => {
    if (active) hold(key)
    else flush()
  }

  const setFine = (key, value) => {
    const current = stateRef.current
    if (!current) return
    if (key === "brightness" && !current.connected) return
    const limit = key === "veil" ? current.veilMax : key === "warmth" ? current.warmthMax : current.contrastMax
    const next = clamp(value, 0, limit)
    hold(key)
    patchLocal({ [key]: next })
    schedule({ [key]: next })
  }

  const choosePreset = async (id) => {
    const current = stateRef.current
    const preset = current?.presets?.find((item) => item.id === id)
    if (!preset) return
    patchLocal({
      brightness: current.connected ? preset.brightness : current.brightness,
      veil: preset.veil,
      warmth: preset.warmth,
      preset: id,
    })
    setDraft(String(current.connected ? preset.brightness : current.brightness))
    inflight.current += 1
    try {
      mergeServer(await applyPreset(id))
    } catch {
      missed.current = true
    } finally {
      inflight.current = Math.max(0, inflight.current - 1)
    }
  }

  const commitDraft = () => {
    editing.current = false
    const current = stateRef.current
    if (!current) return
    const parsed = Number.parseInt(draft, 10)
    if (!Number.isFinite(parsed)) {
      setDraft(String(current.brightness))
      return
    }
    setBrightness(parsed, true)
  }

  const checkAgain = async () => {
    try {
      mergeServer(await reconnect())
    } catch {
      setLoadError("The monitor still isn't answering.")
    }
  }

  if (loadError && !state) {
    return (
      <main className="flex h-full flex-col justify-center bg-bg px-8 text-ink">
        <h1 className="font-serif text-[40px] leading-none tracking-tight">NightOwl</h1>
        <div role="alert" className="mt-6 flex gap-3 rounded-2xl border border-danger/40 bg-danger/10 px-4 py-3">
          <AlertIcon />
          <div>
            <p className="text-[15px] leading-6">{loadError}</p>
            <button type="button" className="focusable mt-2 text-[14px] font-medium underline-offset-4 hover:underline" onClick={() => window.location.reload()}>
              Try again
            </button>
          </div>
        </div>
      </main>
    )
  }

  if (!state) return <Skeleton />

  const shell = shellHint || state.shell
  const glow = 0.04 + (state.brightness / Math.max(1, state.brightnessMax)) * 0.22
  const presetIndex = state.presets.findIndex((preset) => preset.id === state.preset)
  const marks = marksFor(state.brightnessMax)
  const nearest = marks.reduce((best, mark) => (Math.abs(mark - state.brightness) < Math.abs(best - state.brightness) ? mark : best))

  return (
    <div className="flex h-full justify-center bg-bg">
    <main
      className="relative flex h-full w-full max-w-[456px] flex-col bg-bg text-ink shadow-[inset_0_0_0_1px_rgba(243,238,230,0.08)]"
      style={{
        backgroundImage: `radial-gradient(90% 46% at 50% 28%, rgba(240,161,74,${glow.toFixed(3)}), transparent 68%)`,
      }}
    >
      <h1 className="sr-only">Brightness for {state.monitor.title}</h1>
      <header className="flex shrink-0 items-center gap-2 px-3 pt-3">
        <div className="pywebview-drag-region flex min-w-0 flex-1 items-center gap-2.5 px-2 py-2">
          <Mark />
          <p className="text-[15px] font-medium tracking-tight">NightOwl</p>
        </div>
        {shell && (
          <div className="flex">
            <IconButton label="Minimize" onClick={() => windowAction("minimize")}>
              <span className="block h-px w-3.5 bg-current" />
            </IconButton>
            <IconButton label="Hide" onClick={() => windowAction("close")}>
              <CloseIcon />
            </IconButton>
          </div>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-2">
        <div className="flex items-start justify-between gap-4 pt-4">
          <div className="min-w-0">
            <p className="truncate text-[22px] font-medium tracking-tight">{state.monitor.title}</p>
            {state.monitor.detail && <p className="mt-1 text-[14px] leading-5 text-muted">{state.monitor.detail}</p>}
            {state.monitor.mode && <p className="text-[14px] leading-5 text-muted">{state.monitor.mode}</p>}
          </div>
          <p className="mt-1.5 flex shrink-0 items-center gap-2 text-[14px] text-muted">
            <span className={`size-1.5 rounded-full ${state.connected ? "bg-accent" : "bg-danger"}`} aria-hidden="true" />
            {state.connected ? "Live" : "Offline"}
          </p>
        </div>

        <section ref={heroRef} className="pt-6" aria-labelledby="brightness-label">
          <div className="flex items-baseline justify-center">
            <p className="numeral" aria-hidden="true">
              {editing.current ? draft || "0" : state.brightness}
            </p>
            <span className="ml-2 text-[16px] tabular-nums text-muted">/ {state.brightnessMax}</span>
          </div>
          <div className="mt-4 flex items-center justify-between gap-4">
            <p id="brightness-label" className="text-[14px] text-muted">
              Brightness
            </p>
            <label className="flex items-center gap-2 text-[14px] text-muted">
              Exact
              <input
                id="exact"
                className="exact"
                inputMode="numeric"
                autoComplete="off"
                spellCheck={false}
                aria-label="Exact brightness"
                value={draft}
                disabled={!state.connected}
                onFocus={(event) => {
                  editing.current = true
                  event.target.select()
                }}
                onChange={(event) => setDraft(event.target.value.replace(/[^\d]/g, "").slice(0, 3))}
                onBlur={commitDraft}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    event.currentTarget.blur()
                  }
                  if (event.key === "Escape") {
                    editing.current = false
                    setDraft(String(state.brightness))
                    event.currentTarget.blur()
                  }
                  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
                    event.preventDefault()
                    const step = event.shiftKey ? 10 : 1
                    const direction = event.key === "ArrowUp" ? step : -step
                    setBrightness(stateRef.current.brightness + direction, true)
                  }
                }}
              />
            </label>
          </div>

          {state.error && (
            <div role="alert" className="mt-5 flex gap-3 rounded-2xl border border-danger/40 bg-danger/10 px-3.5 py-3">
              <AlertIcon />
              <div>
                <p className="text-[14px] leading-5">{state.error}</p>
                {!state.connected && (
                  <button type="button" className="focusable mt-2 text-[14px] font-medium underline-offset-4 hover:underline" onClick={checkAgain}>
                    Check again
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="mt-4 grid grid-cols-[44px_minmax(0,1fr)_44px] items-center gap-x-4">
            <StepButton
              label="Decrease brightness"
                disabled={state.brightness <= 0}
              onStep={() => setBrightness(stateRef.current.brightness - 1)}
            >
              <Sun size={16} />
            </StepButton>
            <input
              id="brightness"
              className="range"
              type="range"
              min={0}
              max={state.brightnessMax}
              step={1}
              value={state.brightness}
              style={{ "--fill": `${(state.brightness / Math.max(1, state.brightnessMax)) * 100}%` }}
              aria-labelledby="brightness-label"
              aria-valuetext={`${state.brightness} of ${state.brightnessMax}`}
              aria-describedby="brightness-help"
              onPointerDown={() => hold("brightness")}
              onPointerUp={() => flush()}
              onPointerCancel={() => flush()}
              onChange={(event) => setBrightness(Number(event.target.value))}
              onKeyDown={(event) => {
                if (!event.shiftKey) return
                if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return
                event.preventDefault()
                const direction = event.key === "ArrowRight" || event.key === "ArrowUp" ? 10 : -10
                setBrightness(stateRef.current.brightness + direction, true)
              }}
            />
            <StepButton
              label="Increase brightness"
                disabled={state.brightness >= state.brightnessMax}
              onStep={() => setBrightness(stateRef.current.brightness + 1)}
            >
              <Sun size={20} />
            </StepButton>
            <span />
            <div className="flex justify-between px-3.5 text-[14px] tabular-nums text-muted">
              {marks.map((mark) => (
                <span key={mark} className={mark === nearest ? "text-ink" : undefined}>
                  {mark}
                </span>
              ))}
            </div>
          </div>
          <p id="brightness-help" className="sr-only">
            Ctrl, Alt, and Shift with the up or down arrow changes the backlight from anywhere. Shift plus an arrow key jumps by 10.
          </p>
        </section>

        <div
          role="radiogroup"
          aria-label="Brightness presets"
          className="relative mt-6 grid grid-cols-4 rounded-full bg-white/[0.04] p-1"
          onKeyDown={(event) => {
            if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return
            event.preventDefault()
            const current = Math.max(0, presetIndex)
            const direction = event.key === "ArrowRight" ? 1 : -1
            const next = state.presets[(current + direction + state.presets.length) % state.presets.length]
            next && choosePreset(next.id)
          }}
        >
          {presetIndex >= 0 && (
            <span
              className="preset-pill pointer-events-none absolute bottom-1 left-1 top-1 rounded-full bg-accent transition-transform duration-200 ease-out"
              style={{
                width: "calc((100% - 8px) / 4)",
                transform: `translateX(calc(${presetIndex} * 100%))`,
              }}
              aria-hidden="true"
            />
          )}
          {state.presets.map((preset) => {
            const selected = preset.id === state.preset
            return (
              <button
                key={preset.id}
                type="button"
                role="radio"
                aria-checked={selected}
                className={`focusable relative z-10 h-10 rounded-full text-[14px] font-medium ${selected ? "text-[#1a1208]" : "text-[#ddd6cc] hover:text-ink"}`}
                onClick={() => choosePreset(preset.id)}
              >
                {preset.label}
              </button>
            )
          })}
        </div>

        <div className="mt-8 h-px bg-line" />

        <div className="grid gap-6 py-6">
          <FineSlider
            id="veil"
            label="Deeper dark"
            hint="Extra darkness on top of brightness. It stays on when the window is hidden."
            value={state.veil}
            max={state.veilMax}
            onEngage={(active) => engage("veil", active)}
            onChange={(value) => setFine("veil", value)}
          />
          <FineSlider
            id="warmth"
            label="Warmth"
            hint="A light warm tint. The picture stays readable."
            value={state.warmth}
            max={state.warmthMax}
            onEngage={(active) => engage("warmth", active)}
            onChange={(value) => setFine("warmth", value)}
          />
          <FineSlider
            id="contrast"
            label="Contrast"
            hint="50 is the normal picture. Lower looks flatter, higher looks stronger."
            value={state.contrast}
            max={state.contrastMax}
            onEngage={(active) => engage("contrast", active)}
            onChange={(value) => setFine("contrast", value)}
          />
        </div>
      </div>

      <footer className="shrink-0 px-6 pb-5 pt-1">
        <div className="flex items-center justify-between gap-4">
          <p className="text-[14px] text-muted">Scroll the tray icon</p>
          <p className="text-[14px] text-muted">{state.connected ? "DDC/CI" : "No link"}</p>
        </div>
        <p className="mt-3 text-[13px] leading-5 text-muted">
          Made by{" "}
          <a className="credit focusable rounded-sm" href="https://jibanahammed.com/" target="_blank" rel="noreferrer">
            J1BON
          </a>
        </p>
        <p className="text-[13px] leading-5 text-muted">
          <a className="credit focusable rounded-sm" href="https://github.com/J1BON" target="_blank" rel="noreferrer">
            GitHub
          </a>
          <span aria-hidden="true"> · </span>
          <a className="credit focusable rounded-sm" href="https://jibanahammed.com/" target="_blank" rel="noreferrer">
            jibanahammed.com
          </a>
          <span aria-hidden="true"> · </span>
          <a className="credit focusable rounded-sm" href="mailto:jibanahammed8@gmail.com">
            jibanahammed8@gmail.com
          </a>
        </p>
      </footer>
    </main>
    </div>
  )
}

function FineSlider({ id, label, hint, value, max, disabled, onChange, onEngage }) {
  const fill = max ? (value / max) * 100 : 0
  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <label htmlFor={id} className="text-[15px]">
          {label}
        </label>
        <span className="tabular-nums text-[15px] text-muted">{value}</span>
      </div>
      <input
        id={id}
        className="range range-quiet"
        type="range"
        min={0}
        max={max}
        step={1}
        value={value}
        disabled={disabled}
        style={{ "--fill": `${fill}%` }}
        aria-valuetext={`${value} of ${max}`}
        aria-describedby={`${id}-hint`}
        onPointerDown={() => onEngage(true)}
        onPointerUp={() => onEngage(false)}
        onPointerCancel={() => onEngage(false)}
        onChange={(event) => onChange(Number(event.target.value))}
        onKeyUp={() => onEngage(false)}
      />
      <p id={`${id}-hint`} className="text-[14px] leading-5 text-muted">
        {hint}
      </p>
    </div>
  )
}

function StepButton({ label, disabled, onStep, children }) {
  const action = useRef(onStep)
  action.current = onStep
  const fromPointer = useRef(false)
  const timers = useRef({ delay: 0, repeat: 0 })

  const stop = () => {
    window.clearTimeout(timers.current.delay)
    window.clearInterval(timers.current.repeat)
  }

  useEffect(() => {
    window.addEventListener("blur", stop)
    return () => {
      window.removeEventListener("blur", stop)
      stop()
    }
  }, [])

  return (
    <button
      type="button"
      className="focusable grid h-11 w-11 place-items-center rounded-full text-ink hover:bg-white/5 disabled:text-[#9c948a]"
      aria-label={label}
      disabled={disabled}
      onPointerDown={(event) => {
        if (event.button !== 0 || disabled) return
        fromPointer.current = true
        action.current()
        timers.current.delay = window.setTimeout(() => {
          timers.current.repeat = window.setInterval(() => action.current(), 80)
        }, 360)
      }}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      onClick={() => {
        if (fromPointer.current) {
          fromPointer.current = false
          return
        }
        action.current()
      }}
    >
      {children}
    </button>
  )
}

function IconButton({ label, onClick, children }) {
  return (
    <button
      type="button"
      className="focusable grid h-11 w-11 place-items-center rounded-full text-muted hover:bg-white/5 hover:text-ink"
      aria-label={label}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function Mark() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#f0a14a" d="M14.2 2.8a8.6 8.6 0 1 0 7 14.2A7.2 7.2 0 1 1 14.2 2.8z" />
    </svg>
  )
}

function Sun({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <circle cx="12" cy="12" r={size > 18 ? 4 : 3.1} />
      <path strokeLinecap="round" d="M12 2.8v2M12 19.2v2M2.8 12h2M19.2 12h2M5.1 5.1l1.4 1.4M17.5 17.5l1.4 1.4M18.9 5.1l-1.4 1.4M6.5 17.5l-1.4 1.4" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path strokeLinecap="round" d="M2 2l10 10M12 2 2 12" />
    </svg>
  )
}

function AlertIcon() {
  return (
    <svg className="mt-0.5 shrink-0 text-danger" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path strokeLinecap="round" d="M12 7.5v5.5" />
      <circle cx="12" cy="16.5" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  )
}

function Skeleton() {
  return (
    <main className="flex h-full flex-col bg-bg px-6 py-5" aria-busy="true" aria-label="Loading brightness">
      <div className="skeleton h-4 w-28 rounded-full" />
      <div className="skeleton mt-8 h-7 w-56 rounded-lg" />
      <div className="skeleton mt-3 h-4 w-44 rounded-full" />
      <div className="skeleton mt-2 h-4 w-52 rounded-full" />
      <div className="skeleton mx-auto mt-12 h-24 w-36 rounded-2xl" />
      <div className="skeleton mt-8 h-11 rounded-full" />
      <div className="skeleton mt-6 h-11 rounded-full" />
      <div className="mt-8 grid gap-5">
        <div className="skeleton h-16 rounded-xl" />
        <div className="skeleton h-16 rounded-xl" />
        <div className="skeleton h-16 rounded-xl" />
      </div>
    </main>
  )
}
