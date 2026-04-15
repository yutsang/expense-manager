interface StatusBadgeProps {
  status: string;
}

const STATUS_CLASSES: Record<string, string> = {
  // Gray / muted
  draft: "bg-muted text-muted-foreground",
  hard_closed: "bg-muted text-muted-foreground",
  audited: "bg-muted text-muted-foreground",

  // Green — positive / complete
  posted: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  paid: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  active: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  authorised: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  approved: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",

  // Amber / yellow — in-progress / awaiting
  awaiting_approval: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  partial: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  sent: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",

  // Red — voided / archived
  void: "bg-red-100 text-red-600 dark:bg-red-900/20 dark:text-red-400",
  voided: "bg-red-100 text-red-600 dark:bg-red-900/20 dark:text-red-400",
  archived: "bg-red-100 text-red-600 dark:bg-red-900/20 dark:text-red-400",

  // Blue — open
  open: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",

  // Orange — soft closed
  soft_closed: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",

  // Purple — credit note
  credit_note: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

function labelFor(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const cls = STATUS_CLASSES[status] ?? "bg-blue-100 text-blue-700";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {labelFor(status)}
    </span>
  );
}
