import { useEffect, useRef, useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Loader2, Sparkles } from "lucide-react"
import { toast } from "sonner"
import { z } from "zod"

import { ParticipantsMultiSelect } from "@/components/ParticipantsMultiSelect"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useCreateMeeting, useUpdateMeeting } from "@/hooks/useMeetings"
import { api, ApiError } from "@/lib/api"
import { toDateInput, toTimeInput } from "@/lib/calendar"
import type { Meeting, MeetingCreate, ParsedAgenda } from "@/types"

const meetingSchema = z
  .object({
    title: z.string().trim().min(1, "Title is required").max(200, "Max 200 characters"),
    description: z.string().max(5000, "Max 5000 characters"),
    call_link: z.union([
      z.literal(""),
      z.url({ protocol: /^https?$/, message: "Enter a valid http(s) URL" }),
    ]),
    place: z.string().trim().max(255, "Max 255 characters"),
    date: z.string().min(1, "Date is required"),
    start_time: z.string().min(1, "Start time is required"),
    end_time: z.string().min(1, "End time is required"),
    participants: z.array(z.object({ id: z.string(), name: z.string(), email: z.string() })),
  })
  .refine((values) => values.call_link !== "" || values.place !== "", {
    message: "Provide a call link, a place, or both",
    path: ["place"],
  })
  .refine(
    (values) => !values.start_time || !values.end_time || values.end_time > values.start_time,
    {
      message: "End must be after start",
      path: ["end_time"],
    },
  )

type MeetingFormValues = z.infer<typeof meetingSchema>

/** Defaults to the next full hour, one hour long, kept within the same day. */
function emptyValues(start?: Date): MeetingFormValues {
  if (!start) {
    start = new Date()
    start.setHours(start.getHours() + 1, 0, 0, 0)
  }
  const end = new Date(start.getTime() + 60 * 60_000)
  return {
    title: "",
    description: "",
    call_link: "",
    place: "",
    date: toDateInput(start),
    start_time: toTimeInput(start),
    end_time: end.getDate() === start.getDate() ? toTimeInput(end) : "23:59",
    participants: [],
  }
}

function meetingValues(meeting: Meeting): MeetingFormValues {
  const start = new Date(meeting.starts_at)
  return {
    title: meeting.title,
    description: meeting.description ?? "",
    call_link: meeting.call_link ?? "",
    place: meeting.place ?? "",
    date: toDateInput(start),
    start_time: toTimeInput(start),
    end_time: toTimeInput(new Date(meeting.ends_at)),
    participants: meeting.participants,
  }
}

function formatAgendaDescription(agenda: ParsedAgenda): string {
  const parts: string[] = []
  if (agenda.items && agenda.items.length > 0) {
    parts.push("Agenda:")
    agenda.items.forEach((item, idx) => {
      const details: string[] = []
      if (item.owner) details.push(item.owner)
      if (item.minutes) details.push(`${item.minutes} min`)
      const suffix = details.length > 0 ? ` (${details.join(", ")})` : ""
      parts.push(`${idx + 1}. ${item.topic}${suffix}`)
    })
  }

  if (agenda.action_items && agenda.action_items.length > 0) {
    if (parts.length > 0) parts.push("")
    parts.push("Action items:")
    agenda.action_items.forEach((item) => {
      const details: string[] = []
      if (item.owner) details.push(item.owner)
      if (item.due) details.push(`due ${item.due}`)
      const suffix = details.length > 0 ? ` (${details.join(", ")})` : ""
      parts.push(`- ${item.task}${suffix}`)
    })
  }
  return parts.join("\n")
}

function SuggestedBadge() {
  return (
    <span className="ml-2 inline-flex items-center rounded border border-amber-500/30 bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
      suggested
    </span>
  )
}

const API_FIELD_TO_FORM: Record<string, keyof MeetingFormValues> = {
  title: "title",
  description: "description",
  call_link: "call_link",
  place: "place",
  participant_ids: "participants",
  starts_at: "start_time",
  ends_at: "end_time",
}

interface MeetingFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Prefills the date and time, e.g. from a clicked calendar slot. */
  initialStart?: Date
  /** Edits this meeting instead of creating a new one. */
  meeting?: Meeting | null
}

export function MeetingFormDialog({
  open,
  onOpenChange,
  initialStart,
  meeting,
}: MeetingFormDialogProps) {
  const createMeeting = useCreateMeeting()
  const updateMeeting = useUpdateMeeting()
  const saving = createMeeting.isPending || updateMeeting.isPending

  const [rawText, setRawText] = useState("")
  const [isParsing, setIsParsing] = useState(false)
  const [parseError, setParseError] = useState<string | null>(null)
  const [suggestedFields, setSuggestedFields] = useState<Set<string>>(new Set())
  const [aiSuggestion, setAiSuggestion] = useState<{
    model: string
    prompt_version: string
    suggested: ParsedAgenda
  } | null>(null)

  const abortControllerRef = useRef<AbortController | null>(null)

  const form = useForm<MeetingFormValues>({
    resolver: zodResolver(meetingSchema),
    defaultValues: meeting ? meetingValues(meeting) : emptyValues(initialStart),
  })

  const resetAiState = () => {
    setRawText("")
    setParseError(null)
    setIsParsing(false)
    setSuggestedFields(new Set())
    setAiSuggestion(
      meeting?.ai_suggestion
        ? (meeting.ai_suggestion as {
            model: string
            prompt_version: string
            suggested: ParsedAgenda
          })
        : null,
    )
  }

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      resetAiState()
    }
    onOpenChange(nextOpen)
  }

  useEffect(() => {
    if (open) {
      form.reset(meeting ? meetingValues(meeting) : emptyValues(initialStart))
    }
  }, [open, initialStart, meeting, form])

  const removeSuggested = (field: string) => {
    setSuggestedFields((prev) => {
      if (!prev.has(field)) return prev
      const next = new Set(prev)
      next.delete(field)
      return next
    })
  }

  const handleParseAgenda = async () => {
    if (!rawText.trim()) return

    setIsParsing(true)
    setParseError(null)
    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const today = toDateInput(new Date())
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Kyiv"
      const res = await api.parseAgenda({ text: rawText, today, tz }, controller.signal)

      const agenda = res.agenda
      const newSuggested = new Set<string>()

      if (agenda.title) {
        form.setValue("title", agenda.title, { shouldValidate: true })
        newSuggested.add("title")
      }

      if (agenda.starts_at) {
        const parsedStart = new Date(agenda.starts_at)
        if (!isNaN(parsedStart.getTime())) {
          form.setValue("date", toDateInput(parsedStart), { shouldValidate: true })
          form.setValue("start_time", toTimeInput(parsedStart), { shouldValidate: true })
          newSuggested.add("date")
          newSuggested.add("start_time")

          const durationMin = agenda.duration_minutes ?? 60
          const parsedEnd = new Date(parsedStart.getTime() + durationMin * 60_000)
          form.setValue("end_time", toTimeInput(parsedEnd), { shouldValidate: true })
          newSuggested.add("end_time")
        }
      } else if (agenda.duration_minutes) {
        const currentDate = form.getValues("date")
        const currentStart = form.getValues("start_time")
        if (currentDate && currentStart) {
          const startDate = new Date(`${currentDate}T${currentStart}`)
          if (!isNaN(startDate.getTime())) {
            const endDate = new Date(startDate.getTime() + agenda.duration_minutes * 60_000)
            form.setValue("end_time", toTimeInput(endDate), { shouldValidate: true })
            newSuggested.add("end_time")
          }
        }
      }

      const formattedDesc = formatAgendaDescription(agenda)
      if (formattedDesc) {
        form.setValue("description", formattedDesc, { shouldValidate: true })
        newSuggested.add("description")
      }

      setSuggestedFields(newSuggested)
      setAiSuggestion({
        model: res.model,
        prompt_version: res.prompt_version,
        suggested: agenda,
      })
      toast.success("Agenda parsed! Suggested fields are marked below.")
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        toast.info("Parsing cancelled")
        return
      }
      let msg = "Failed to parse agenda. You can enter details manually."
      if (err instanceof ApiError) {
        if (err.status === 413) {
          msg = "Text is too long (maximum 10,000 characters)."
        } else if (err.status === 422) {
          msg = "The model could not find an agenda in the pasted text."
        } else if (err.status === 429) {
          msg = "Service is busy (throttling), please try again shortly."
        } else if (err.message) {
          msg = err.message
        }
      } else if (err instanceof Error) {
        msg = err.message
      }
      setParseError(msg)
      toast.error(msg)
    } finally {
      setIsParsing(false)
      abortControllerRef.current = null
    }
  }

  const handleCancelParse = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsParsing(false)
  }

  const onSubmit = async (values: MeetingFormValues) => {
    const data: MeetingCreate = {
      title: values.title,
      description: values.description.trim() || null,
      call_link: values.call_link || null,
      place: values.place || null,
      starts_at: new Date(`${values.date}T${values.start_time}`).toISOString(),
      ends_at: new Date(`${values.date}T${values.end_time}`).toISOString(),
      participant_ids: values.participants.map((p) => p.id),
      ...(aiSuggestion
        ? { ai_suggestion: aiSuggestion as unknown as Record<string, unknown> }
        : {}),
    }
    try {
      if (meeting) {
        await updateMeeting.mutateAsync({ id: meeting.id, data })
        toast.success("Meeting updated")
      } else {
        await createMeeting.mutateAsync(data)
        toast.success("Meeting created")
      }
      onOpenChange(false)
    } catch (error) {
      if (error instanceof ApiError && error.status === 422 && error.issues.length > 0) {
        for (const issue of error.issues) {
          const field = API_FIELD_TO_FORM[String(issue.loc[1])]
          form.setError(field ?? "root", { message: issue.msg })
        }
        return
      }
      toast.error(
        error instanceof Error ? error.message : `Could not ${meeting ? "save" : "create"} meeting`,
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{meeting ? "Edit meeting" : "New meeting"}</DialogTitle>
          <DialogDescription>
            Add a call link, a place, or both so people know where to go.
          </DialogDescription>
        </DialogHeader>

        {/* Paste an agenda section */}
        <div className="space-y-2 rounded-lg border bg-muted/40 p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              <span>Paste an agenda</span>
            </div>
            <span className="text-[11px] text-muted-foreground">AI suggests, you decide</span>
          </div>
          <Textarea
            placeholder="Paste meeting notes, emails, chat messages... (e.g. 'Sync tomorrow at 10am: 1. Review PRs 20m 2. Demo 15m')"
            value={rawText}
            onChange={(e) => {
              setRawText(e.target.value)
              setParseError(null)
            }}
            rows={3}
            disabled={isParsing}
            className="bg-background text-xs"
          />
          {parseError && (
            <div className="rounded border border-destructive/20 bg-destructive/10 p-2 text-xs text-destructive">
              {parseError}
            </div>
          )}
          <div className="flex items-center justify-between pt-0.5">
            {isParsing ? (
              <div className="flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                <span className="text-xs text-muted-foreground">
                  Parsing agenda with Claude (2–8s)…
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs text-destructive hover:bg-destructive/10"
                  onClick={handleCancelParse}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="ml-auto h-7 gap-1.5 text-xs font-medium"
                onClick={handleParseAgenda}
                disabled={!rawText.trim()}
              >
                <Sparkles className="h-3 w-3" />
                Parse with AI
              </Button>
            )}
          </div>
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="flex items-center">
                    <span>Title</span>
                    {suggestedFields.has("title") && <SuggestedBadge />}
                  </FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Sprint planning"
                      {...field}
                      onChange={(e) => {
                        removeSuggested("title")
                        field.onChange(e)
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-[1.4fr_1fr_1fr]">
              <FormField
                control={form.control}
                name="date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center">
                      <span>Date</span>
                      {suggestedFields.has("date") && <SuggestedBadge />}
                    </FormLabel>
                    <FormControl>
                      <Input
                        type="date"
                        {...field}
                        onChange={(e) => {
                          removeSuggested("date")
                          field.onChange(e)
                        }}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="start_time"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center">
                      <span>Start</span>
                      {suggestedFields.has("start_time") && <SuggestedBadge />}
                    </FormLabel>
                    <FormControl>
                      <Input
                        type="time"
                        {...field}
                        onChange={(e) => {
                          removeSuggested("start_time")
                          field.onChange(e)
                        }}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="end_time"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center">
                      <span>End</span>
                      {suggestedFields.has("end_time") && <SuggestedBadge />}
                    </FormLabel>
                    <FormControl>
                      <Input
                        type="time"
                        {...field}
                        onChange={(e) => {
                          removeSuggested("end_time")
                          field.onChange(e)
                        }}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="flex items-center">
                    <span>Description</span>
                    {suggestedFields.has("description") && <SuggestedBadge />}
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="What is this meeting about?"
                      rows={3}
                      {...field}
                      onChange={(e) => {
                        removeSuggested("description")
                        field.onChange(e)
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="participants"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Participants</FormLabel>
                  <FormControl>
                    <ParticipantsMultiSelect value={field.value} onChange={field.onChange} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="call_link"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Call link</FormLabel>
                    <FormControl>
                      <Input type="url" placeholder="https://meet.google.com/…" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="place"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Place</FormLabel>
                    <FormControl>
                      <Input placeholder="Room 204" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {form.formState.errors.root && (
              <p className="text-sm text-destructive">{form.formState.errors.root.message}</p>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {meeting
                  ? saving
                    ? "Saving…"
                    : "Save changes"
                  : saving
                    ? "Creating…"
                    : "Create meeting"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
