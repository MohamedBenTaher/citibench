import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { TriangleAlertIcon } from "lucide-react";

export function ErrorAlert({
  title = "Request failed",
  message,
}: {
  title?: string;
  message: string;
}) {
  return (
    <Alert variant="destructive">
      <TriangleAlertIcon />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="break-words">{message}</AlertDescription>
    </Alert>
  );
}
