#set document(title: "$document_title")
#set page(paper: "a4", margin: (x: 2.5cm, y: 2cm))
#set text(font: "Liberation Sans", size: 11pt, lang: "$lang")

#align(center)[
  $logo_block
  #v(0.3cm)
  $title_block
]

#v(0.5cm)
#line(length: 100%, stroke: 0.5pt)
#v(0.3cm)

#table(
  columns: (auto, 1fr), stroke: none, inset: 4pt,
  [*$lbl_ticket:*], [\#$ticket_id ($ticket_number)],
  [*$lbl_subject:*], [$subject],
  [*$lbl_sender:*], [$user_name],
  [*$lbl_created:*], [$date_display],
  [*$lbl_processed:*], [$today_display],
)

#v(0.3cm)
== $lbl_message

$message

#v(0.3cm)
== $lbl_attachments

$attachments_block
