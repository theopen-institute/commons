def full_name(doc):
	"""The name parts that are filled in, joined in reading order."""
	parts = (doc.first_name, doc.middle_name, doc.last_name)
	return " ".join(part.strip() for part in parts if part and part.strip())
