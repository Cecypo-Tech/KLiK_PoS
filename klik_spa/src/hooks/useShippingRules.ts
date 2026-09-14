import { useState, useEffect } from "react";

export interface ShippingRuleOption {
  name: string;
  label?: string;
  calculate_based_on?: "Fixed" | "Net Total" | "Net Weight" | string;
  shipping_amount?: number;
}

/** Selling Shipping Rules for the active till's company. Skips the request when disabled. */
export function useShippingRules(enabled: boolean) {
  const [rules, setRules] = useState<ShippingRuleOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setRules([]);
      return;
    }

    let cancelled = false;
    const fetchShippingRules = async () => {
      try {
        setLoading(true);
        const response = await fetch("/api/method/klik_pos.api.shipping_rule.get_shipping_rules", {
          method: "GET",
          headers: { Accept: "application/json" },
          credentials: "include",
        });

        const data = await response.json();
        if (!response.ok || !Array.isArray(data?.message)) {
          throw new Error("Failed to fetch shipping rules");
        }
        if (!cancelled) setRules(data.message);
      } catch (err: unknown) {
        console.error("Error loading shipping rules:", err);
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchShippingRules();
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { rules, loading, error };
}
