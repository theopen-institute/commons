import { h } from 'vue'
import { toast } from 'frappe-ui'
import { deskUrl } from './reconciliation'

/** A document a toast names, as a link. */
export interface DocumentRef {
  doctype: string
  name: string
}

/**
 * A success toast that links to the documents a write created or matched,
 * each opening in the desk in a new tab.
 *
 * A VNode rather than an HTML string: frappe-ui passes a string through
 * DOMPurify, which keeps `<a href>` but strips `target`, so a link in a string
 * would take the reader away from the page. Built here from the document's
 * name, nothing in it comes from outside. Shown for longer than a plain toast,
 * so there is time to click it.
 */
export function toastWithLinks(message: string, documents: DocumentRef[]) {
  const links = documents.flatMap((document, index) => [
    index ? ', ' : ' ',
    h(
      'a',
      {
        href: deskUrl(document.doctype, document.name),
        target: '_blank',
        rel: 'noopener',
        class: 'whitespace-nowrap font-medium underline',
      },
      document.name,
    ),
  ])
  toast.success(h('span', [message, ...links]), { duration: 10_000 })
}
