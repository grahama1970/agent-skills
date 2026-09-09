type Order = {
  id: string
  label: string
}

export function RepeatedEntityStable({ orders }: { orders: Order[] }) {
  return (
    <ul>
      {orders.map((order) => (
        <li key={order.id}>
          <button
            data-qid={`orders:item:open:${order.id}`}
            data-qs-action="ORDERS_OPEN"
            title={`Open ${order.label}`}
            onClick={() => {}}
          >
            Open
          </button>
        </li>
      ))}
    </ul>
  )
}
