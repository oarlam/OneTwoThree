import { useEffect } from "react"
import { LoaderCircle } from "lucide-react"

import { authConfig, redirectToCognitoLogin } from "@/lib/auth"

export function CognitoLoginPage() {
  useEffect(() => {
    const { domain, clientId } = authConfig()
    if (domain && clientId) {
      void redirectToCognitoLogin()
    }
  }, [])

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-4">
      <div className="flex items-center gap-3 text-lg font-medium text-muted-foreground">
        <LoaderCircle className="size-6 animate-spin text-primary" />
        Redirecting to Cognito sign-in…
      </div>
      <button
        type="button"
        onClick={() => void redirectToCognitoLogin()}
        className="mt-4 text-sm text-primary underline hover:text-primary/80"
      >
        Click here if not redirected automatically
      </button>
    </div>
  )
}
