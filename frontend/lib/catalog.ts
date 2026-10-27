export type Product = {
  id: number;
  name: string;
  image_url: string;
  created_at: string;
};

export type ProductPage = { items: Product[]; next_cursor: number | null };

export async function getProducts(query: string, before?: string): Promise<ProductPage> {
  const params = new URLSearchParams({ limit: "24" });
  if (query) params.set("q", query);
  if (before && /^[1-9][0-9]{0,14}$/.test(before)) params.set("before", before);
  const response = await fetch(
    `${process.env.API_BASE_URL || "http://api:8000"}/api/products?${params}`,
    { cache: "no-store", signal: AbortSignal.timeout(10_000) },
  );
  if (!response.ok) throw new Error("Catalog API unavailable");
  return response.json() as Promise<ProductPage>;
}
