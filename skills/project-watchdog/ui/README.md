# Project Watchdog UI

React/Tailwind control-tower view for `project-watchdog` receipts.

## Run

```bash
cd ..
./run.sh ui-data --receipt-limit 100 --output ui/public/project-watchdog-snapshot.json
cd ui
npm install
npm run dev
```

The UI reads `/project-watchdog-snapshot.json` and falls back to bundled sample
receipt data when that file is absent. It is read-only: mutations still go
through `../run.sh tick`, `$ticket`, `$project-watchdog`, `$ask`, and Tau receipt
lanes.

## Gates

```bash
npm run build
npm run check:contract
```

`check:contract` verifies the `data-qid`, `data-qs-action`, `title`,
`useRegisterAction`, desktop table, mobile card, sticky filter, embedded
Tau React Flow DAG, and receipt-chain literals required by the watchdog UI
contract.
