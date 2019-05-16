import buildkite.mastermind

access_doc = buildkite.mastermind.get_access_document({
    'BUILDKITE_REPO': 'https://git.corp.tc/infra/ami-builder',
    'BUILDKITE_COMMIT': '5ebbab8f751a95ee67bf6e71ef94e98e86f56ef9',
    'AWS_ASSUME_ROLE': 'arn:something'
})

print(access_doc)
