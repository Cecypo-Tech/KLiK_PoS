def build_item_search_conditions(search: str, enhanced: bool) -> tuple[list[str], list]:
	"""Return (sql_clauses, params) to append to an item listing query.

	enhanced=False - one term, anywhere in the item code, item name or a barcode. The
	                 description is left to the enhanced search: it is the longest column
	                 and the default search runs three times per request.
	enhanced=True  - multi-token AND: every whitespace-delimited word must appear in at
	                 least one of item code, item name, description, or barcode.

	The clauses are written for a query that aliases `tabItem` as `i`.
	"""
	if not search or not search.strip():
		return [], []

	columns = ["i.name", "i.item_name"] + (["i.description"] if enhanced else [])
	tokens = search.strip().split() if enhanced else [search.strip()]
	like_columns = "\n\t\t\t\tOR ".join(f"{column} LIKE %s" for column in columns)
	clause = f"""AND (
				{like_columns}
				OR EXISTS (
					SELECT 1 FROM `tabItem Barcode` ib
					WHERE ib.parent = i.name AND ib.barcode LIKE %s
				)
			)"""

	clauses: list[str] = []
	params: list = []
	for token in tokens:
		clauses.append(clause)
		params.extend([f"%{token}%"] * (len(columns) + 1))

	return clauses, params
