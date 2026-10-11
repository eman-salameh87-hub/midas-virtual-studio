export type RecordedGenerationCost = {
  output_id?: string | null;
  amount?: number | null;
  currency?: string | null;
  status?: string | null;
};

export function isKnownRecordedCost(
  cost: RecordedGenerationCost | null | undefined,
): cost is RecordedGenerationCost & { amount: number } {
  return Boolean(
    cost &&
      cost.status === "known" &&
      typeof cost.amount === "number" &&
      Number.isFinite(cost.amount),
  );
}

export function formatRecordedAmount(amount: number): string {
  return String(amount);
}

function formatKnownAmount(cost: RecordedGenerationCost & { amount: number }): string {
  const amount = formatRecordedAmount(cost.amount);
  const currency = typeof cost.currency === "string" ? cost.currency.trim() : "";
  if (!currency) return amount;
  if (currency.toUpperCase() === "USD") return `$${amount}`;
  return `${amount} ${currency}`;
}

export function formatCostLine(
  label: string,
  cost: RecordedGenerationCost | null | undefined,
): string {
  if (!isKnownRecordedCost(cost)) return "Cost unavailable";
  return `${label}: ${formatKnownAmount(cost)}`;
}

export function costBelongsToOutput(
  cost: RecordedGenerationCost | null | undefined,
  outputId: string | null,
): boolean {
  if (!cost || !outputId) return false;
  return cost.output_id === outputId;
}
