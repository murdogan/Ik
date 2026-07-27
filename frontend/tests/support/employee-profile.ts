export function employeeProfileInsights(limit = 20) {
  return {
    documents: {
      missing: 0,
      available: 0,
      expiring: 0,
      expired: 0,
    },
    leave: {
      period_year: 2026,
      remaining_balance_days: 0,
      pending_request_count: 0,
    },
    profile_changes: {
      submitted_request_count: 0,
      latest_status: null,
      latest_submitted_at: null,
    },
    activity: {
      items: [],
      limit,
      next_cursor: null,
    },
  };
}
