from musicarch.view_state import RecordViewState


def _sample_records() -> list[dict]:
    return [
        {"old_file_name": "a.mp3", "new_file_name": "a.mp3", "status": "pending", "cloud_match_result": "待匹配"},
        {"old_file_name": "b.mp3", "new_file_name": "b.mp3", "status": "anomaly", "cloud_match_result": "异常"},
        {"old_file_name": "c.mp3", "new_file_name": "c.mp3", "status": "success", "cloud_match_result": "匹配"},
        {"old_file_name": "d.mp3", "new_file_name": "d.mp3", "status": "anomaly", "cloud_match_result": "未找到"},
    ]


def test_filter_by_status():
    state = RecordViewState()
    state.set_records(_sample_records())

    page = state.build(
        status_filter="anomaly",
        keyword="",
        sort_key="old_file_name",
        descending=False,
        page_size=100,
        page_index=0,
    )

    assert page.total_filtered == 2
    assert page.indices == [1, 3]


def test_keyword_filter_and_sort_desc():
    state = RecordViewState()
    state.set_records(_sample_records())

    page = state.build(
        status_filter="全部",
        keyword="mp3",
        sort_key="old_file_name",
        descending=True,
        page_size=100,
        page_index=0,
    )

    assert page.total_filtered == 4
    assert page.indices[0] == 3


def test_pagination_slices_result():
    state = RecordViewState()
    state.set_records(_sample_records())

    page = state.build(
        status_filter="全部",
        keyword="",
        sort_key="old_file_name",
        descending=False,
        page_size=2,
        page_index=1,
    )

    assert page.total_pages == 2
    assert page.page_index == 1
    assert page.indices == [2, 3]


def test_page_index_clamped():
    state = RecordViewState()
    state.set_records(_sample_records())

    page = state.build(
        status_filter="全部",
        keyword="",
        sort_key="old_file_name",
        descending=False,
        page_size=2,
        page_index=99,
    )

    assert page.page_index == 1
