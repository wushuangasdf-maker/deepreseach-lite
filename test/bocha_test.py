from bocha_search import bocha_search, build_context

def test_bochar(query:str,count:int):
    pages=bocha_search(query,count)
    context=build_context(pages)
    return context
