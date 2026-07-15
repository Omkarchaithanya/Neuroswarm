package okf

// Go OKF SDK stub — HTTP client against /okf/*.

type QueryRequest struct {
	Text         string `json:"text"`
	AgentProfile string `json:"agent_profile"`
	TokenBudget  int    `json:"token_budget"`
}

// Client talks to OKF serve endpoints.
type Client struct {
	BaseURL string
}
