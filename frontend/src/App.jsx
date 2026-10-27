import React, { useState } from "react";
import { api } from "./api.js";
import { useLoad } from "./hooks.js";
import { clock, dateTime, dayLabel, mw, num, pct, shortDay } from "./format.js";
import { DayChart, ErrorBars, MonthChart, COLORS } from "./charts.jsx";

function Stat({ label, value, note }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

/* iOS-style activity indicator: 12 bars that fade around the wheel */
function Spinner({ label = "Loading" }) {
  return (
    <div className="loader" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true">
        {Array.from({ length: 12 }, (_, i) => (
          <i key={i} style={{ transform: `rotate(${i * 30}deg)`, animationDelay: `${-(1 - i / 12)}s` }} />
        ))}
      </span>
      <span className="loader-text">{label}...</span>
    </div>
  );
}

function Status({ state, children }) {
  if (state.loading) return <Spinner label="Loading forecast" />;
  if (state.error) return <p className="status error">{state.error.message}</p>;
  return children;
}

function Legend({ items }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span key={i.label}>
          <span className="swatch" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ buying view */
function BuyView({ date, cutoff }) {
  const [showActual, setShowActual] = useState(false);
  const state = useLoad(
    () => api.decision({ decision_date: date, cutoff_hour: cutoff.hour, cutoff_minute: cutoff.minute }),
    `${date}|${clock(cutoff)}`
  );
  return (
    <Status state={state}>
      {state.data && <BuyBody d={state.data} cutoff={cutoff} showActual={showActual} setShowActual={setShowActual} />}
    </Status>
  );
}

function BuyBody({ d, cutoff, showActual, setShowActual }) {
  const s = d.summary;
  const b = s.bands;
  const hasActual = d.series.some((p) => p.actual != null);
  return (
    <>
      <header className="view-head">
        <h1>Wind forecast for {dayLabel(d.delivery_date)}</h1>
        <p>
          Decision made on {dayLabel(d.decision_date)} by {clock(cutoff)} UK time. These are the latest forecasts that had been published by
          then (issued {dateTime(s.first_publish)} to {dateTime(s.last_publish)}).
        </p>
      </header>

      <section className="stats">
        <Stat label="Average wind expected" value={mw(s.mean_forecast)} />
        <Stat label="Peak half-hour" value={mw(s.peak_forecast)} />
        <Stat label="Lowest half-hour" value={mw(s.min_forecast)} />
        <Stat label="Wind you can rely on" value={mw(s.mean_reliable)} note="average of the low end of the likely range" />
      </section>

      <section>
        <div className="chart-head">
          <h2>Half-hourly forecast and likely range</h2>
          {hasActual && (
            <label className="check">
              <input type="checkbox" checked={showActual} onChange={(e) => setShowActual(e.target.checked)} />
              Show what actually happened
            </label>
          )}
        </div>
        <Legend
          items={[
            { label: "Forecast", color: COLORS.forecast },
            { label: "Likely range (10th to 90th percentile)", color: COLORS.band },
            ...(showActual ? [{ label: "Actual", color: COLORS.actual }] : []),
          ]}
        />
        <DayChart series={d.series} showActual={showActual} />
        <p className="footnote">
          The range adds the 10th and 90th percentile of past forecast errors to each forecast.{" "}
          {b.basis === "prior_days"
            ? `It uses ${b.days} earlier delivery days whose actuals were known at decision time.`
            : "There are too few earlier days for this date, so the range uses all January errors and is optimistic for this day."}{" "}
          Planning on the low end of the range means wind should beat it about 9 half-hours in 10.
        </p>
      </section>
    </>
  );
}

/* --------------------------------------------------------------- accuracy view */
function AccuracyView({ cutoff }) {
  const state = useLoad(() => api.evaluation({ cutoff_hour: cutoff.hour, cutoff_minute: cutoff.minute }), clock(cutoff));
  return <Status state={state}>{state.data && <AccuracyBody d={state.data} cutoff={cutoff} />}</Status>;
}

function AccuracyBody({ d, cutoff }) {
  const m = d.metrics;
  const bias = m.bias;
  return (
    <>
      <header className="view-head">
        <h1>How accurate was the forecast?</h1>
        <p>
          Using only forecasts available by {clock(cutoff)} the day before delivery, the forecast missed by {num(m.mae)} MW on average (
          {pct(m.wmape_pct)} of actual output) over {num(m.n)} half-hours of January delivery.{" "}
          {Math.abs(bias) < 0.02 * m.mean_actual
            ? "There was no strong tendency to over- or under-forecast."
            : bias > 0
            ? `Wind tended to beat the forecast by ${num(bias)} MW.`
            : `Wind tended to fall short of the forecast by ${num(-bias)} MW.`}
        </p>
      </header>

      <section className="stats">
        <Stat label="Average miss" value={mw(m.mae)} note={`${pct(m.wmape_pct)} of average output`} />
        <Stat label="Bad half-hour (1 in 10)" value={mw(m.p90_abs_err)} note="miss in either direction" />
        <Stat label="Overstated wind by (1 in 10)" value={mw(m.p90_shortfall)} note="extra power you would have had to buy" />
        <Stat label="Overstated wind by (1 in 20)" value={mw(m.p95_shortfall)} note={`forecast was too high in ${pct(m.overforecast_share_pct, 0)} of half-hours`} />
      </section>

      <section>
        <h2>Forecast vs actual, whole month</h2>
        <Legend items={[{ label: "Forecast at decision time", color: COLORS.forecast }, { label: "Actual", color: COLORS.actual }]} />
        <MonthChart series={d.series} />
      </section>

      <section className="two-col">
        <div>
          <h2>Average miss by time of day</h2>
          <p className="footnote">Where in the day you need the biggest safety margin.</p>
          <ErrorBars data={d.by_slot} xKey="slot" />
        </div>
        <div>
          <h2>Average miss by forecast age</h2>
          <p className="footnote">Hours between the forecast being issued and the half-hour it covers.</p>
          <ErrorBars data={d.by_horizon} xKey="label" />
        </div>
      </section>

      <section>
        <h2>Average miss by delivery day</h2>
        <p className="footnote">Some days are much harder to call than others. Hover for the day's bias.</p>
        <ErrorBars data={d.by_day} xKey="delivery_date" xFormat={(v) => shortDay(new Date(`${v}T12:00:00Z`).getTime())} highlight={m.mae} />
      </section>

      <section>
        <h2>Does the cutoff time matter?</h2>
        <p className="footnote">A later cutoff lets you use fresher forecasts. Average miss by cutoff:</p>
        <table className="table">
          <thead>
            <tr>
              <th>Cutoff (UK)</th>
              <th>Average miss</th>
              <th>% of output</th>
            </tr>
          </thead>
          <tbody>
            {d.cutoff_sensitivity.map((r) => (
              <tr key={`${r.hour}:${r.minute}`} className={r.hour === cutoff.hour && r.minute === cutoff.minute ? "current" : ""}>
                <td>{clock(r)}</td>
                <td>{mw(r.mae)}</td>
                <td>{pct(r.wmape_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

/* ------------------------------------------------------------------------ shell */
export default function App() {
  const meta = useLoad(api.meta, "meta");
  const [view, setView] = useState("buy");
  const [cutoffKey, setCutoffKey] = useState(null);
  const [date, setDate] = useState(null);

  if (meta.loading)
    return (
      <div className="page-loader">
        <Spinner label="Loading Wind Forecast Desk" />
      </div>
    );
  if (meta.error)
    return (
      <div className="page">
        <h1>Data not available</h1>
        <p className="status error">{meta.error.message}</p>
        <p>Run <code>python backend/scripts/fetch_data.py</code> to download the January 2026 Elexon data, then restart the server.</p>
      </div>
    );

  const m = meta.data;
  const choices = m.cutoff_choices;
  const cutoff = choices.find((c) => clock(c) === cutoffKey) ?? m.default_cutoff;
  const decisionDate = date ?? "2026-01-15";

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <div className="brand-name">Wind Forecast Desk</div>
          <div className="brand-sub">GB day-ahead wind, national level</div>
        </div>

        <nav className="nav" aria-label="Views">
          <button className={view === "buy" ? "active" : ""} onClick={() => setView("buy")}>
            Tomorrow's wind
          </button>
          <button className={view === "accuracy" ? "active" : ""} onClick={() => setView("accuracy")}>
            Forecast accuracy
          </button>
        </nav>

        <div className="controls">
          <label>
            Cutoff (UK time)
            <select value={clock(cutoff)} onChange={(e) => setCutoffKey(e.target.value)}>
              {choices.map((c) => (
                <option key={clock(c)} value={clock(c)}>
                  {clock(c)}
                </option>
              ))}
            </select>
          </label>
          {view === "buy" && (
            <label>
              Decision day
              <input type="date" value={decisionDate} min={m.decision_start} max={m.decision_end} onChange={(e) => e.target.value && setDate(e.target.value)} />
            </label>
          )}
        </div>

        <p className="source">
          Source: Elexon Insights API (FUELHH wind actuals, WINDFOR wind forecasts). Purchase decisions made 1 to 31 January 2026.
          {m.fetched_at ? ` Data fetched ${new Date(m.fetched_at).toLocaleDateString("en-GB")}.` : ""}
        </p>
      </aside>

      <main className="main">{view === "buy" ? <BuyView date={decisionDate} cutoff={cutoff} /> : <AccuracyView cutoff={cutoff} />}</main>
    </div>
  );
}