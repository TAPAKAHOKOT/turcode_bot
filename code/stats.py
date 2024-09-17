from datetime import datetime, timedelta

from code.models import Payout, PayoutActionEnum


async def get_stats(settings, stat_date=None):
    # Определяем сегодняшнюю дату и даты за последние 5 дней
    if stat_date is not None:
        dates = [stat_date.strftime('%d.%m.%Y')]
    else:
        today = datetime.now().date()
        dates = [(today - timedelta(days=i)).strftime('%d.%m.%Y') for i in range(7)]

    stats = {}
    async with settings.db_session() as session:
        for date in dates:
            success_payouts_count = await Payout.get_count_by_date_and_action(
                session=session,
                bot_name=settings.bot_name,
                date_str=date,
                action=PayoutActionEnum.SUCCESS.code,
            )
            success_payouts_amount_sum = await Payout.get_amount_sum_by_date_and_action(
                session=session,
                bot_name=settings.bot_name,
                date_str=date,
                action=PayoutActionEnum.SUCCESS.code,
            )
            fail_payouts_count = await Payout.get_count_by_date_and_action(
                session=session,
                bot_name=settings.bot_name,
                date_str=date,
                action=PayoutActionEnum.FAIL.code,
            )
            fail_payouts_amount_sum = await Payout.get_amount_sum_by_date_and_action(
                session=session,
                bot_name=settings.bot_name,
                date_str=date,
                action=PayoutActionEnum.FAIL.code,
            )

            if success_payouts_count or fail_payouts_count:
                stats[date] = {
                    'success_payouts_count': success_payouts_count,
                    'success_payouts_amount_sum': success_payouts_amount_sum,
                    'success_payouts_avg': int(
                        success_payouts_amount_sum / success_payouts_count) if success_payouts_count else 0,
                    'fail_payouts_count': fail_payouts_count,
                    'fail_payouts_amount_sum': fail_payouts_amount_sum,
                    'fail_payouts_avg': int(fail_payouts_amount_sum / fail_payouts_count) if fail_payouts_count else 0,
                }

    return stats
