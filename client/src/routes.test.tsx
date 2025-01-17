import { createAddressPageRoutes, isAddressPageRoute } from "routes";

describe("isAddressPageRoute()", () => {
  it("correctly identifies a regular address page", () => {
    expect(isAddressPageRoute("/es/address/QUEENS/4125/CASE%20STREET")).toBe(true);
  });

  it("correctly identifies a legacy address page", () => {
    expect(isAddressPageRoute("/es/legacy/address/QUEENS/4125/CASE%20STREET")).toBe(true);
  });

  it("correctly identifies a regular page as not an address page", () => {
    expect(isAddressPageRoute("/en/legacy/how-to-use")).toBe(false);
  });

  it("handles cases where 'address' happens to be in the url somewhere", () => {
    expect(isAddressPageRoute("/en/find-my-address")).toBe(false);
  });
});

describe("createAddressPageRoutes()", () => {
  const OLD_ENV = process.env;

  // https://stackoverflow.com/questions/48033841/test-process-env-with-jest
  beforeEach(() => {
    jest.resetModules(); // Most important - it clears the cache
    process.env = { ...OLD_ENV }; // Make a copy
  });

  afterAll(() => {
    process.env = OLD_ENV; // Restore old environment
  });

  it("prefixes with string when given one", () => {
    expect(createAddressPageRoutes("/boop").timeline).toBe("/boop/timeline");
  });

  it("prefixes with address page params when given one", () => {
    expect(
      createAddressPageRoutes({
        boro: "BROOKLYN",
        housenumber: "654",
        streetname: "PARK PLACE",
      }).timeline
    ).toBe("/address/BROOKLYN/654/PARK%20PLACE/timeline");
  });

  it("prefixes with address page params and locale when given one", () => {
    expect(
      createAddressPageRoutes({
        boro: "BROOKLYN",
        housenumber: "654",
        streetname: "PARK PLACE",
        locale: "es",
      }).timeline
    ).toBe("/es/address/BROOKLYN/654/PARK%20PLACE/timeline");
  });

  it("correctly sets the right path when route is specified as a legacy route", () => {
    process.env.REACT_APP_ENABLE_NEW_WOWZA_PORTFOLIO_MAPPING = "1";
    expect(
      createAddressPageRoutes(
        {
          boro: "BROOKLYN",
          housenumber: "654",
          streetname: "PARK PLACE",
          locale: "es",
        },
        true
      ).timeline
    ).toBe("/es/legacy/address/BROOKLYN/654/PARK%20PLACE/timeline");
  });

  it("defaults to the standard path when env variable is not defined", () => {
    process.env.REACT_APP_ENABLE_NEW_WOWZA_PORTFOLIO_MAPPING = undefined;
    expect(
      createAddressPageRoutes(
        {
          boro: "BROOKLYN",
          housenumber: "654",
          streetname: "PARK PLACE",
          locale: "es",
        },
        true
      ).timeline
    ).toBe("/es/address/BROOKLYN/654/PARK%20PLACE/timeline");
  });
});
