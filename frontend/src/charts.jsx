import React from "react";
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine,
} from "recharts";
import { num, shortDay, slotOf, dateTime } from "./format.js";

export const COLORS = {
  forecast: "#0F6E8C",
  actual: "#1B2A33",
  band: "#BFD9E3",
  warn: "#A63D2F",
  grid: "#DCE3E8",
  axis: "#5C6B75",
};

const axisProps = { stroke: COLORS.axis, tick: { fontSize: 12, fill: COLORS.axis }, tickLine: false };

function TipBox({ title, rows }) {
  return (
    <div className="tip">
      <strong>{title}</strong>
      {rows.map((r) => (
        <div key={r.label}>
          <span className="swatch" style={{ background: r.color }} />
          {r.label}: {r.value}
        </div>
      ))}
    </div>
  );
}

/** One delivery day: forecast line, plausible range band, optional actuals. */
export function DayChart({ series, showActual }) {
  const data = series.map((p) => ({
    t: new Date(p.startTime).getTime(),
    forecast: p.forecast,
    actual: showActual ? p.actual : null,
    low: p.low,
    span: p.high - p.low,
    high: p.high,
    published: p.publishTime,
  }));
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t) => slotOf(new Date(t).toISOString())} {...axisProps} tickCount={9} />
        <YAxis {...axisProps} width={56} tickFormatter={num} />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload;
            const rows = [
              { label: "Forecast", value: `${num(d.forecast)} MW`, color: COLORS.forecast },
              { label: "Likely range", value: `${num(d.low)} to ${num(d.high)} MW`, color: COLORS.band },
            ];
            if (d.actual != null) rows.push({ label: "Actual", value: `${num(d.actual)} MW`, color: COLORS.actual });
            rows.push({ label: "Forecast issued", value: dateTime(d.published), color: "transparent" });
            return <TipBox title={slotOf(new Date(d.t).toISOString())} rows={rows} />;
          }}
        />
        <Area dataKey="low" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area dataKey="span" stackId="band" stroke="none" fill={COLORS.band} fillOpacity={0.7} isAnimationActive={false} />
        <Line dataKey="forecast" stroke={COLORS.forecast} strokeWidth={2.5} dot={false} isAnimationActive={false} />
        {showActual && <Line dataKey="actual" stroke={COLORS.actual} strokeWidth={1.75} strokeDasharray="5 3" dot={false} isAnimationActive={false} />}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Whole month: decision-time forecast vs actual. */
export function MonthChart({ series }) {
  const data = series.map((p) => ({ t: new Date(p.startTime).getTime(), forecast: p.forecast, actual: p.actual }));
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={shortDay} {...axisProps} tickCount={8} />
        <YAxis {...axisProps} width={56} tickFormatter={num} />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload;
            return (
              <TipBox
                title={dateTime(new Date(d.t).toISOString())}
                rows={[
                  { label: "Forecast", value: `${num(d.forecast)} MW`, color: COLORS.forecast },
                  { label: "Actual", value: `${num(d.actual)} MW`, color: COLORS.actual },
                ]}
              />
            );
          }}
        />
        <Line dataKey="actual" stroke={COLORS.actual} strokeWidth={1.25} dot={false} isAnimationActive={false} />
        <Line dataKey="forecast" stroke={COLORS.forecast} strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Generic MAE bar chart. */
export function ErrorBars({ data, xKey, xFormat, height = 240, highlight }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey={xKey} tickFormatter={xFormat} {...axisProps} interval="preserveStartEnd" minTickGap={18} />
        <YAxis {...axisProps} width={56} tickFormatter={num} />
        <Tooltip
          cursor={{ fill: "rgba(15,110,140,0.08)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload;
            return (
              <TipBox
                title={xFormat ? xFormat(d[xKey]) : String(d[xKey])}
                rows={[
                  { label: "Average miss", value: `${num(d.mae)} MW`, color: COLORS.forecast },
                  { label: "Bias (actual - forecast)", value: `${num(d.bias)} MW`, color: COLORS.warn },
                  { label: "Half-hours", value: String(d.n), color: "transparent" },
                ]}
              />
            );
          }}
        />
        <Bar dataKey="mae" fill={COLORS.forecast} radius={[2, 2, 0, 0]} isAnimationActive={false} />
        {highlight != null && <ReferenceLine y={highlight} stroke={COLORS.warn} strokeDasharray="4 3" />}
      </BarChart>
    </ResponsiveContainer>
  );
}
