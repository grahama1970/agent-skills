# data-join-immutable-data

**Severity**: warn
**Category**: data-join

## Rule

Never mutate the data array in place. Always pass a new array reference to `.data()`. D3's join diffing relies on reference identity for the key function to work correctly.

## Bad

```typescript
data.push(newPoint);  // mutates existing array
svg.selectAll("circle").data(data, d => d.id).join("circle");
```

## Good

```typescript
const updated = [...data, newPoint];  // new array reference
svg.selectAll("circle").data(updated, d => d.id).join("circle");
```

## Why

Mutating the source array breaks React integration (no re-render trigger), confuses D3's internal diffing when the same array reference is passed, and makes debugging data flow impossible.
