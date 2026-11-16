"""Specification constants: table sizes, per-column nulls, enums, boundaries, formulas."""
from __future__ import annotations

TABLE_SIZES = {'Repo': 40, 'Solution': 120, 'Method': 200, 'MethodParameter': 400}

NULL_SHARES = {
    ('Solution', 'RepoId'): 0.15,
    ('Solution', 'Path'): 0.15,
    ('Method', 'SolutionId'): 0.15,
    ('Method', 'Lang'): 0.15,
    ('Method', 'Summary'): 0.175,
    ('Method', 'Name'): 0.15,
    ('Method', 'FullComment'): 0.15,
    ('MethodParameter', 'MethodId'): 0.15,
    ('MethodParameter', 'Name'): 0.15,
    ('MethodParameter', 'Type'): 0.15,
}

LANG_ENUM = ['en', 'fr', 'fi', 'it', 'af', 'ca', 'ro', 'de', 'EN', 'IT', '']
LANG_BOUNDARY = ['en', 'EN', 'it', 'IT', '', 'x']
LANG_DOMAIN = list(dict.fromkeys(LANG_ENUM + ['x']))

FLAG_BOUNDARY = [0, 1]

STARS_BOUNDARY = [1998, 1999, 2000, 2001]
FORKS_BOUNDARY = [2, 3, 4, 999, 1000, 1001]
WATCHERS_BOUNDARY = [0, 1, 1000, 5000]

STARS_HEAVY = 2000
STARS_HEAVY_MIN_ROWS = 2

REPO_BOUNDARY_LITERALS = [1, 2, 3, 149, 150, 151]
SOLUTION_BOUNDARY_LITERALS = [1, 2, 17, 18, 19]
METHOD_SOLUTION_BOUNDARY_LITERALS = [0, 1, 2, 17, 18, 19, 149, 150, 151]

TICK_LO = 636430000000000000
TICK_HI = 636480000000000000

FRESH_VALUE_SHARE = 0.3

URL_POOL = [
    'https://github.com/wallerdev/htmlsharp.git',
    'https://github.com/unclebob/nslim.git',
    'https://github.com/maravillas/linq-to-delicious.git',
    'https://github.com/mauriciodeamorim/tdd.encontro2.git',
    'https://github.com/aroder/heatmap.git',
    'https://github.com/managedfusion/managedfusion.git',
    'https://github.com/maff/se3ue6.git',
    'https://github.com/maxild/playground.git',
    'https://github.com/derickbailey/presentations-and-training.git',
]
PATH_POOL = [
    'wallerdev_htmlsharp\\HtmlSharp.sln',
    'maravillas_linq-to-delicious\\tasty.sln',
    'mauriciodeamorim_tdd.encontro2\\Tdd.Encontro2.sln',
    'aroder_heatmap\\CenStatsHeatMap.sln',
    'managedfusion_managedfusion\\ManagedFusion.sln',
    'maff_se3ue6\\US6.sln',
    'maxild_playground\\Playground.sln',
    'jeffdik_tachy\\examples\\Example1\\Example1.sln',
]
NAME_POOL = [
    'HtmlSharp.HtmlParser.Feed',
    'HtmlSharp.HtmlParser.ParseDoctypeElement',
    'IQ.Data.DbQueryProvider.GetQueryText',
    'IQ.Data.DbQueryProvider.Execute',
    'IQ.Data.DbQueryProvider.GetExecutionPlan',
    'IQ.Data.DbQueryProvider.Translate',
    'IQ.Data.DbQueryProvider.CanBeEvaluatedLocally',
    'IQ.Data.DbQueryProvider.Project',
]
TYPE_POOL = [
    'System.String', 'System.Int32', 'System.Linq.Expressions.Expression',
    'IQ.Data.SelectExpression', 'IQ.Data.QueryCommand', 'System.Object[]',
    'System.Data.Common.DbDataReader', 'System.Func',
]
PARAM_NAME_POOL = ['data', 'i', 'declstartpos', 'expression', 's', 'query',
                   'paramValues', 'reader']
COMMENT_POOL = [
    'Feeds data into the parser',
    ' interneral -- scan past <!ELEMENT declarations',
    ' Converts the query expression into text that corresponds to the command that would be executed.',
    ' Execute the query expression (does translation, etc.)',
    ' Convert the query expression into an execution plan',
    ' Do all query translations execpt building the execution plan',
    ' Determines whether a given expression can be executed locally.',
    ' Execute an actual query specified in the target language using the sADO connection',
]
SUMMARY_POOL = [
    'Converts the query expression into text that corresponds to the command that would be executed.  Useful for debugging.',
    'Execute the query expression ',
    'Convert the query expression into an execution plan',
    'Do all query translations execpt building the execution plan',
    'Determines whether a given expression can be executed locally.  ',
    'Execute an actual query specified in the target language using the sADO connection',
    'Converts a data reader into a sequence of objects using a projector function on each row',
    'Get an IEnumerable that will execute the specified query when enumerated',
]
API_POOL = [
    'System.String.IsNullOrEmpty HtmlSharp.HtmlParser.GoAhead HtmlSharp.HtmlParser.EndData HtmlSharp.HtmlParser.PopTag',
    'HtmlSharp.HtmlParser.ScanName System.Collections.Generic.KeyValuePair.Value System.String.Substring',
    'IQ.Data.DbQueryProvider.Translate IQ.Data.QueryLanguage.Format IQ.Data.SelectGatherer.Gather',
    'System.Linq.Expressions.LambdaExpression.Body IQ.Data.DbQueryProvider.Translate',
    'System.Linq.Expressions.ConstantExpression.Value System.Linq.IQueryable.Provider',
    'IQ.Data.QueryCommand.CommandText IQ.Data.QueryCommand.ParameterNames',
]
TOKENIZED_POOL = [
    'html parser feed',
    'html parser parse doctype element',
    'db query provider get query text',
    'db query provider execute',
    'db query provider get execution plan',
    'db query provider translate',
    'db query provider can be evaluated locally',
    'db query provider project',
]
