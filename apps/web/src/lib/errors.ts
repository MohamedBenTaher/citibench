export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ValidationErrorItem = {
  msg?: string;
  message?: string;
};

export function formatApiDetail(detail: unknown): string | undefined {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (!item || typeof item !== "object") {
        return [];
      }
      const row = item as ValidationErrorItem;
      const message = row.msg ?? row.message;
      return typeof message === "string" ? [message] : [];
    });
    return messages.length > 0 ? messages.join("; ") : undefined;
  }
  if (detail && typeof detail === "object") {
    const row = detail as ValidationErrorItem;
    const message = row.msg ?? row.message;
    if (typeof message === "string") {
      return message;
    }
  }
  return undefined;
}
