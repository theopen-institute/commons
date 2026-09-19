import { watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/**
 * Open this page's "raise one" dialog when the address asks for it.
 *
 * The search bar offers "New leave request" the way the desk's Awesome Bar
 * offers "New ToDo", and it has the same problem to solve: the form belongs to
 * a page the bar is not on. The desk answers it with `frappe.new_doc`, which
 * can because every desk form is a route. Here the form is a dialog owned by
 * one page, so the bar asks for that page with `?new=1` and the page opens it.
 *
 * The flag is taken back out of the address as soon as it is read. It is an
 * instruction, not a state: leaving it there would reopen the dialog on a
 * reload, and put a page in the history that reopens it on the way back.
 */
export function useNewRequestQuery(open: Ref<boolean>) {
  const route = useRoute()
  const router = useRouter()

  watch(
    () => route.query.new,
    (asked) => {
      if (!asked) return
      open.value = true
      const query = { ...route.query }
      delete query.new
      router.replace({ query })
    },
    // Immediate, because arriving at the page *is* the event: the query is
    // already there by the time this runs.
    { immediate: true },
  )
}
