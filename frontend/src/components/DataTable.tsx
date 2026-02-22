// eslint-disable-next-line @typescript-eslint/no-explicit-any
interface Column<T extends Record<string, any>> {
  key: keyof T | string;
  header: string;
  render?: (row: T) => React.ReactNode;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
interface Props<T extends Record<string, any>> {
  data: T[];
  columns: Column<T>[];
  emptyMessage?: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function DataTable<T extends Record<string, any>>({ data, columns, emptyMessage = "No data" }: Props<T>) {
  if (data.length === 0) {
    return <p className="text-sm text-gray-500 py-4 text-center">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50">
            {columns.map((col) => (
              <th key={col.key as string} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data.map((row, i) => (
            <tr key={i} className="hover:bg-gray-50">
              {columns.map((col) => (
                <td key={col.key as string} className="px-3 py-2 text-gray-700">
                  {col.render ? col.render(row) : String(row[col.key as keyof T] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
