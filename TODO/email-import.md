# Import bills from email (IMAP)

Suppliers send bills by email as PDF attachments. Reading a mailbox would save downloading and
uploading each one.

- A mailbox the household forwards bills to (or the suppliers send to), read over IMAP with
  credentials from the environment or a secret file.
- On the scheduler's tick: fetch new messages, take PDF attachments, read each as "Upload a bill"
  does, and hold the result as a draft for a person to check; never save a bill unseen.
- Duplicates: the reader's file and invoice-number checks already apply.
- Notify the household that drafts are waiting, and mark or move processed messages.
