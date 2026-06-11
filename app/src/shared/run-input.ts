export interface ProtocolConfig {
  topic: boolean
  papers: boolean
  authors: boolean
}

export interface QueryFilters {
  openAccessOnly: boolean
  humansOnly: boolean
  excludeReviews: boolean
  excludeCaseReports: boolean
}

export interface RunInputPaper {
  title?: string
  pmid?: string
  doi?: string
  pmc?: string
  issn?: string
  url: string
  source?: string
  journal?: string
  authors?: string[]
  citationCount?: number
  compositeScore?: number
  recommendationScore?: number
  geneticsScore?: number
  pubYear?: string
  abstract?: string
  publicationTypes?: string[]
  searchRank?: number
  original?: string
  isOpenAccess?: boolean
}

export type RunInputMode = 'standard' | 'review_all' | 'new_from_query' | 'added_only'

export interface RunInputSnapshot {
  schemaVersion: 1
  protocolName: string
  activeModules: ProtocolConfig
  baseQuery: string
  constructedQuery: string
  startYear: string
  endYear: string
  filters: QueryFilters
  topicPapers: RunInputPaper[]
  specificPmids: string[]
  specificPapers: RunInputPaper[]
  authorPapers: RunInputPaper[]
  columns: Record<string, string>
  selectedPmids: string[]
  runPmids: string[]
  runMode: RunInputMode
  sourceJobId?: string
}
