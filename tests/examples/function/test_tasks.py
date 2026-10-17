from app.tasks import Reorder

# Reorder takes any callable, so a test hands it a stand-in for low_stock —
# no Project/Context needed, same as the function tests next to this file.


def test_reorder_asks_the_injected_function_with_its_threshold():
    asked: list[int] = []

    def find_shortages(threshold: int) -> list[str]:
        asked.append(threshold)
        return ["apple"]

    assert Reorder(find_shortages).execute() == ["apple"]
    assert asked == [15]
