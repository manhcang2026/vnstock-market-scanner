export default function AccountShell({ navigation, center, context }) {
  return (
    <div className="account-workspace">
      <aside className="account-left-rail">{navigation}</aside>
      <section className="account-center">{center}</section>
      <aside className="account-right-rail">{context}</aside>
    </div>
  )
}
