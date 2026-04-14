import { redirect } from "next/navigation";

// Root → redirect to dashboard (auth check happens in middleware)
export default function RootPage() {
  redirect("/dashboard");
}
