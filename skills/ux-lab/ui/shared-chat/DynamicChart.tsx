import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import DataModal from './DataModal';
import { csvEscape, triggerCSVDownload } from './downloadUtils';
import { useRegisterAction } from './_support/useRegisterAction';

type ChartKind = 'line' | 'bar';
type ChartDatum = Record<string, string | number | null | undefined>;

interface ChartPayload {
  type: ChartKind;
  xAxisKey: string;
  lineKeys: string[];
  dataset: ChartDatum[];
}

interface DynamicChartProps {
  rawJson: string;
}

interface TooltipEntry {
  color?: string;
  name?: string;
  value?: string | number;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
}

const CHART_COLORS = ['#58a6ff', '#3fb950', '#e3b341', '#ff7b72', '#a371f7'];

function parseChartPayload(rawJson: string): ChartPayload | null {
  try {
    const data = JSON.parse(rawJson) as Partial<ChartPayload>;
    if (
      (data.type !== 'line' && data.type !== 'bar')
      || typeof data.xAxisKey !== 'string'
      || !Array.isArray(data.lineKeys)
      || !data.lineKeys.every((key) => typeof key === 'string')
      || !Array.isArray(data.dataset)
    ) {
      return null;
    }
    return data as ChartPayload;
  } catch (error) {
    console.error('Failed to parse chart JSON:', error);
    return null;
  }
}

function CustomTooltip({ active, payload, label }: ChartTooltipProps): JSX.Element | null {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        backgroundColor: 'var(--surface-base)',
        border: '1px solid var(--border-default)',
        borderRadius: 6,
        boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
        padding: 12,
        minWidth: 150,
      }}
    >
      <p style={{ margin: '0 0 8px 0', color: 'var(--text-primary)', fontSize: 12, fontWeight: 700 }}>
        {label}
      </p>
      {payload.map((entry) => (
        <div
          key={`${entry.name}:${entry.value}`}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 16,
            color: entry.color ?? 'var(--text-muted)',
            fontSize: 12,
            marginBottom: 4,
          }}
        >
          <span>{entry.name}</span>
          <span style={{ fontWeight: 700, fontFamily: '"SF Mono", Consolas, monospace' }}>
            {entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function DynamicChart({ rawJson }: DynamicChartProps): JSX.Element {
  const parsedData = useMemo(() => parseChartPayload(rawJson), [rawJson]);
  const [activeType, setActiveType] = useState<ChartKind>('line');
  const [isExpanded, setExpanded] = useState(false);

  useRegisterAction('shared-chat:dynamic-chart:set-line', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_DYNAMIC_CHART_SET_LINE',
    label: 'Show line chart',
    description: 'Render the dynamic chart payload as a line chart',
  });
  useRegisterAction('shared-chat:dynamic-chart:set-bar', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_DYNAMIC_CHART_SET_BAR',
    label: 'Show bar chart',
    description: 'Render the dynamic chart payload as a bar chart',
  });

  useEffect(() => {
    if (parsedData?.type) setActiveType(parsedData.type);
  }, [parsedData]);

  if (!parsedData) {
    return (
      <div
        style={{
          padding: 16,
          backgroundColor: '#440000',
          border: '1px solid #660000',
          borderRadius: 6,
          color: '#ff7b72',
          fontSize: 12,
          fontFamily: '"SF Mono", Consolas, monospace',
          margin: '12px 0',
        }}
      >
        [Chart Render Error]: Invalid JSON payload from execution engine.
      </div>
    );
  }

  const { xAxisKey, lineKeys, dataset } = parsedData;
  const axisProps = {
    stroke: 'var(--text-muted)',
    fontSize: 10,
    tickLine: false,
    axisLine: { stroke: 'var(--border-default)' },
  };

  const exportChartToCSV = () => {
    const headers = [xAxisKey, ...lineKeys].map(csvEscape).join(',');
    const rows = dataset.map((row) => (
      [row[xAxisKey], ...lineKeys.map((key) => row[key])].map(csvEscape).join(',')
    ));
    triggerCSVDownload([headers, ...rows].join('\n'), `sparta_telemetry_${Date.now()}.csv`);
  };

  const renderBrush = (instance: 'inline' | 'modal') => (
    <Brush
      key={`brush-${instance}`}
      dataKey={xAxisKey}
      height={20}
      stroke="var(--border-default)"
      fill="var(--surface-base)"
      travellerWidth={8}
      tickFormatter={() => ''}
    />
  );

  const renderChart = (height: string | number, instance: 'inline' | 'modal') => (
    <ResponsiveContainer height={height} width="100%">
      {activeType === 'bar' ? (
        <BarChart data={dataset}>
          <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3" vertical={false} />
          <XAxis {...axisProps} dataKey={xAxisKey} />
          <YAxis {...axisProps} />
          <Tooltip content={<CustomTooltip />} cursor={false} />
          {lineKeys.map((key, index) => (
            <Bar
              key={key}
              id={`sparta-chart-${instance}-${key}`}
              dataKey={key}
              fill={CHART_COLORS[index % CHART_COLORS.length]}
              radius={[2, 2, 0, 0]}
            />
          ))}
          {renderBrush(instance)}
        </BarChart>
      ) : (
        <LineChart data={dataset}>
          <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3" vertical={false} />
          <XAxis {...axisProps} dataKey={xAxisKey} />
          <YAxis {...axisProps} />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'var(--border-default)' }} />
          {lineKeys.map((key, index) => (
            <Line
              key={key}
              id={`sparta-chart-${instance}-${key}`}
              type="monotone"
              dataKey={key}
              stroke={CHART_COLORS[index % CHART_COLORS.length]}
              strokeWidth={2}
              dot={{ r: 2, fill: 'var(--surface-base)', strokeWidth: 2 }}
              activeDot={{ r: 5 }}
            />
          ))}
          {renderBrush(instance)}
        </LineChart>
      )}
    </ResponsiveContainer>
  );

  const chartToggleButton = (type: ChartKind, label: string) => (
    <button
      type="button"
      data-qid={`shared-chat:dynamic-chart:set-${type}`}
      data-qs-action={type === 'line' ? 'SHARED_CHAT_DYNAMIC_CHART_SET_LINE' : 'SHARED_CHAT_DYNAMIC_CHART_SET_BAR'}
      title={`Show ${label.toLowerCase()} chart`}
      onClick={() => setActiveType(type)}
      style={{
        backgroundColor: activeType === type ? 'var(--border-subtle)' : 'transparent',
        color: activeType === type ? 'var(--text-primary)' : 'var(--text-muted)',
        border: 'none',
        borderRadius: 4,
        padding: '4px 10px',
        fontSize: 10,
        fontFamily: '"SF Mono", Consolas, monospace',
        fontWeight: activeType === type ? 800 : 400,
        cursor: 'pointer',
        transition: 'background-color 0.2s, color 0.2s',
      }}
    >
      {label}
    </button>
  );

  return (
    <>
      <div
        data-qid="shared-chat:dynamic-chart"
        style={{
          position: 'relative',
          width: '100%',
          height: 280,
          backgroundColor: 'var(--surface-sunken)',
          border: '1px solid var(--border-default)',
          borderRadius: 6,
          padding: '34px 16px 12px 0',
          margin: '12px 0',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            display: 'flex',
            gap: 8,
            zIndex: 10,
          }}
        >
          <button
            type="button"
            data-qid="shared-chat:chart:expand"
            onClick={() => setExpanded(true)}
            style={{
              backgroundColor: 'var(--border-subtle)',
              color: 'var(--text-muted)',
              border: '1px solid var(--border-default)',
              borderRadius: 4,
              padding: '4px 8px',
              fontSize: 10,
              fontFamily: '"SF Mono", Consolas, monospace',
              cursor: 'pointer',
              transition: 'color 0.2s, border-color 0.2s',
            }}
            onMouseEnter={(event) => {
              event.currentTarget.style.color = 'var(--text-primary)';
              event.currentTarget.style.borderColor = '#58a6ff';
            }}
            onMouseLeave={(event) => {
              event.currentTarget.style.color = 'var(--text-muted)';
              event.currentTarget.style.borderColor = 'var(--border-default)';
            }}
          >
            EXPAND
          </button>
          <div
            data-qid="shared-chat:chart:segmented-control"
            style={{
              display: 'flex',
              backgroundColor: 'var(--surface-base)',
              border: '1px solid var(--border-default)',
              borderRadius: 6,
              padding: 2,
              gap: 2,
            }}
          >
            {chartToggleButton('line', 'LINE')}
            {chartToggleButton('bar', 'BAR')}
          </div>
        </div>

        {!isExpanded ? renderChart('100%', 'inline') : null}
      </div>

      <DataModal
        isOpen={isExpanded}
        onClose={() => setExpanded(false)}
        title="TELEMETRY VISUALIZATION"
        onExport={exportChartToCSV}
      >
        <div style={{ height: '100%', minHeight: 560, width: '100%' }}>
          {renderChart('100%', 'modal')}
        </div>
      </DataModal>
    </>
  );
}
