"use client";

import { useQuery } from "@tanstack/react-query";

import { StatusPanel } from "@/components/StatusPanel";
import { fetchHealth } from "@/lib/api";

export function SystemStatus() {
  const { data, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5000,
  });
  return <StatusPanel report={data} error={error} />;
}
