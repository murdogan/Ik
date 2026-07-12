export function tokenFromFragment(fragment: string): string | null {
  if (!fragment) {
    return null;
  }

  const parameters = new URLSearchParams(fragment);
  const namedToken = parameters.get("token")?.trim();
  if (namedToken) {
    return namedToken;
  }

  if (fragment.includes("=")) {
    return null;
  }

  try {
    return decodeURIComponent(fragment).trim() || null;
  } catch {
    return null;
  }
}
