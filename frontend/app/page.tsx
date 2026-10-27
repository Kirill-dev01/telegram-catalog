import Link from "next/link";
import { RefreshButton } from "@/components/refresh-button";
import { getProducts, type ProductPage } from "@/lib/catalog";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type SearchParams = Promise<{ q?: string | string[]; before?: string | string[] }>;

export default async function Catalog({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim().slice(0, 120) : "";
  const before = typeof params.before === "string" ? params.before : undefined;
  let page: ProductPage | null = null;
  try {
    page = await getProducts(query, before);
  } catch {
    // A dependency outage must never look like a genuinely empty catalog.
  }
  const nextParams = new URLSearchParams();
  if (query) nextParams.set("q", query);
  if (page?.next_cursor) nextParams.set("before", String(page.next_cursor));

  return (
    <main id="catalog" className="container">
      <header className="heading">
        <div>
          <p className="eyebrow">ТОВАРЫ</p>
          <h1>Каталог</h1>
          <p className="muted">Все товары в одном месте.</p>
        </div>
        <RefreshButton />
      </header>

      <form className="search" action="/" method="get">
        <label className="sr-only" htmlFor="search">Название товара</label>
        <input id="search" name="q" type="search" placeholder="Найти товар по названию"
               defaultValue={query} maxLength={120} />
        <button type="submit">Найти</button>
      </form>

      {(query || before) && <p className="filter-info">
        {query ? <>Поиск: «{query}» · </> : null}<Link href="/">Все товары</Link>
      </p>}

      {!page ? (
        <section className="state" role="alert">
          <h2>Каталог временно недоступен</h2>
          <p>Не удалось загрузить товары. Попробуйте обновить страницу чуть позже.</p>
          <RefreshButton />
        </section>
      ) : page.items.length === 0 ? (
        <section className="state">
          <h2>{query ? "Ничего не найдено" : before ? "Больше товаров нет" : "Пока нет товаров"}</h2>
          <p>{query ? "Попробуйте другое название или откройте все товары." :
            before ? "Вернитесь к началу каталога." : "Новые товары появятся здесь после добавления."}</p>
          {(query || before) && <Link href="/">Открыть каталог</Link>}
        </section>
      ) : (
        <>
          <ul className="product-grid">
            {page.items.map((product) => (
              <li key={product.id} className="product">
                {/* Plain img avoids per-replica image optimization disk caches. */}
                <img src={product.image_url} alt={product.name} width={600} height={450}
                     loading="lazy" decoding="async" />
                <div className="product-body"><h2>{product.name}</h2></div>
              </li>
            ))}
          </ul>
          <nav className="pagination" aria-label="Страницы каталога">
            {before && <Link href={query ? `/?q=${encodeURIComponent(query)}` : "/"}>К началу</Link>}
            {page.next_cursor && <Link className="button" href={`/?${nextParams}`}>Следующие товары →</Link>}
          </nav>
        </>
      )}
      <footer>Каталог товаров</footer>
    </main>
  );
}
