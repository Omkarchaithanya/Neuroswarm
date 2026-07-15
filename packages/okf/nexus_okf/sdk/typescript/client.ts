/**
 * TypeScript OKF SDK stub — HTTP client against /okf/*.
 */
export type OKFQueryRequest = {
  text: string;
  agent_profile?: string;
  token_budget?: number;
};

export class OKFClient {
  constructor(private baseUrl: string) {}

  async query(req: OKFQueryRequest): Promise<any> {
    const res = await fetch(`${this.baseUrl}/okf/query`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(`OKF query failed: ${res.status}`);
    return res.json();
  }
}
