# Repository Coverage (alloydb)

[Full report](https://htmlpreview.github.io/?https://github.com/garybadwal/haystack-core-integrations/blob/python-coverage-comment-action-data-alloydb/htmlcov/index.html)

| Name                                                                             |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/haystack\_integrations/components/retrievers/alloydb/embedding\_retriever.py |       25 |        2 |        2 |        0 |     93% |     73-79 |
| src/haystack\_integrations/components/retrievers/alloydb/keyword\_retriever.py   |       24 |        5 |        2 |        0 |     81% |60-65, 88-90 |
| src/haystack\_integrations/document\_stores/alloydb/converters.py                |       42 |        3 |       18 |        4 |     88% |35-\>45, 38, 68, 71 |
| src/haystack\_integrations/document\_stores/alloydb/document\_store.py           |      456 |      310 |      122 |        9 |     29% |265-266, 272-276, 298-\>exit, 303-\>exit, 343, 352-414, 420-440, 446-484, 493-501, 511-549, 557-586, 594-609, 624-646, 652-663, 682-716, 724-737, 747-754, 768-800, 811-850, 853-861, 871-884, 917-935, 948-950, 970-982, 992-1000, 1010-1025, 1028, 1049-1059, 1067-1084, 1102-1118, 1131-1132, 1134-1138, 1146-1178, 1197-1210, 1219-1241, 1251-1278 |
| src/haystack\_integrations/document\_stores/alloydb/filters.py                   |      144 |       75 |       60 |        5 |     44% |34-36, 48, 70-90, 111, 154, 161, 165-177, 181-193, 197-209, 213-225, 229-232, 236-241, 245-248 |
| **TOTAL**                                                                        |  **691** |  **395** |  **204** |   **18** | **40%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/garybadwal/haystack-core-integrations/python-coverage-comment-action-data-alloydb/badge.svg)](https://htmlpreview.github.io/?https://github.com/garybadwal/haystack-core-integrations/blob/python-coverage-comment-action-data-alloydb/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/garybadwal/haystack-core-integrations/python-coverage-comment-action-data-alloydb/endpoint.json)](https://htmlpreview.github.io/?https://github.com/garybadwal/haystack-core-integrations/blob/python-coverage-comment-action-data-alloydb/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fgarybadwal%2Fhaystack-core-integrations%2Fpython-coverage-comment-action-data-alloydb%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/garybadwal/haystack-core-integrations/blob/python-coverage-comment-action-data-alloydb/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.