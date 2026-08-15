import { queryOptions, useQuery } from "@tanstack/react-query";
import { loadDashboardData } from "./data-source";

export const dashboardQueryOptions = queryOptions({
  queryKey: ["dashboard"],
  queryFn: loadDashboardData,
  staleTime: 30_000,
});

export function useDashboard() {
  return useQuery(dashboardQueryOptions);
}
