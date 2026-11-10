import unittest


def apply_event(state, event):
    result = dict(state)
    changes = event.get("changes", {})
    remove = event.get("remove", [])
    if not isinstance(changes, dict) or not isinstance(remove, list):
        raise ValueError("invalid operation shape")
    if set(changes) & set(remove):
        raise ValueError("a field cannot be assigned and removed together")
    for key in remove:
        if key not in result:
            raise ValueError("cannot remove an absent field")
        del result[key]
    result.update(changes)
    return result


class HistoryOperationsTest(unittest.TestCase):
    def test_missing_key_inherits(self):
        self.assertEqual(apply_event({"a": 1, "b": 2}, {"changes": {"a": 3}}), {"a": 3, "b": 2})

    def test_falsy_and_empty_values_are_assignments(self):
        values = {"zero": 0, "false": False, "null": None, "string": "", "array": []}
        self.assertEqual(apply_event({}, {"changes": values}), values)

    def test_remove_is_distinct(self):
        self.assertEqual(apply_event({"a": 1, "b": ""}, {"remove": ["a"]}), {"b": ""})

    def test_conflict_rejected(self):
        with self.assertRaises(ValueError):
            apply_event({"a": 1}, {"changes": {"a": 0}, "remove": ["a"]})

    def test_absent_remove_rejected(self):
        with self.assertRaises(ValueError):
            apply_event({}, {"remove": ["a"]})


if __name__ == "__main__":
    unittest.main()
