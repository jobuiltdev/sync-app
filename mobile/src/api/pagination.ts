/** The envelope DRF's page-number pagination returns for list endpoints.
 *
 *  Small owned collections (a provider's services, their areas, the catalog
 *  categories) opt out of pagination server-side and return a bare array, so not
 *  every list endpoint uses this. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
