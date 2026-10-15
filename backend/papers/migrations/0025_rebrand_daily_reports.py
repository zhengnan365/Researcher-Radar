from django.db import migrations


def rebrand_daily_reports(apps, schema_editor):
    DailyReport = apps.get_model("papers", "DailyReport")
    for report in DailyReport.objects.all().iterator():
        changed = []
        if report.title.startswith("文献日报 - "):
            report.title = report.title.replace("文献日报 - ", "科研雷达 · 文献日报 - ", 1)
            changed.append("title")
        if report.markdown_content.startswith("# 文献日报 - "):
            report.markdown_content = report.markdown_content.replace(
                "# 文献日报 - ", "# 科研雷达 · 文献日报 - ", 1
            )
            changed.append("markdown_content")
        html = report.html_content
        if "<title>文献日报</title>" in html or "<h1>文献日报 - " in html:
            report.html_content = html.replace(
                "<title>文献日报</title>", "<title>科研雷达 · 文献日报</title>"
            ).replace("<h1>文献日报 - ", "<h1>科研雷达 · 文献日报 - ", 1)
            changed.append("html_content")
        if changed:
            report.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("papers", "0024_login_attempt")]

    operations = [migrations.RunPython(rebrand_daily_reports, migrations.RunPython.noop)]
