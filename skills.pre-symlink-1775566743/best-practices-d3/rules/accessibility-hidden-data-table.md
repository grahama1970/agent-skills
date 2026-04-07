# accessibility-hidden-data-table

**Severity**: error
**Category**: accessibility

## Rule

Provide a visually hidden `<table>` or `<ul>` alongside the SVG/Canvas chart that contains the same data. Screen readers cannot parse visual elements but can read semantic HTML tables.

## Good

```tsx
<div className="chart-container">
  <svg viewBox="..." role="img" aria-label="Revenue by quarter">
    {/* D3 visualization */}
  </svg>

  {/* Visually hidden but accessible to screen readers */}
  <table className="sr-only">
    <caption>Revenue by quarter</caption>
    <thead>
      <tr><th>Quarter</th><th>Revenue</th></tr>
    </thead>
    <tbody>
      {data.map(d => (
        <tr key={d.quarter}>
          <td>{d.quarter}</td>
          <td>${d.revenue.toLocaleString()}</td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}
```

## Why

`aria-label` gives a one-sentence summary. A hidden data table gives full access to the underlying data for screen reader users — they can navigate row by row, sort, and understand exact values. This is the gold standard for chart accessibility (WCAG 1.1.1).
