"""Menu04 allocation estimates using the existing V82 position-gap calculation."""

from copy import deepcopy
from decimal import Decimal, ROUND_DOWN, localcontext

from current_analysis_delivery import source_target_in_currency
from family_input import digest
from formal_mode_analysis import native, native_orders
from fx_conversion import convert


def cash_reference(cash, currency, fx):
    if currency in cash:
        return Decimal(cash[currency]), None
    if len(cash) == 1 and currency and fx:
        source_currency, source_amount = next(iter(cash.items()))
        converted = convert(source_amount, source_currency, currency, fx)
        if converted is not None:
            return converted, {'currency': source_currency, 'amount': source_amount, 'fx_as_of': fx['as_of'],
                               'quote_per_base': fx['quote_per_base']}
    return None, None


def deliver(report, root):
    result = deepcopy(report)
    result.setdefault('component_report_digest', report['report_digest'])
    portfolio = result.get('current_portfolio_reference') or {}
    fx = portfolio.get('reporting_FX')
    positions = {row['symbol']: row for row in portfolio.get('positions', [])}
    cash = (result.get('accepted_owner_financial_facts') or {}).get('accepted_net_available_by_currency') or {}
    deployment, _, _ = native(root)

    for row in result['positions']:
        conclusion = row.get('formal_conclusion') or {}
        position = positions.get(row['symbol'], {})
        currency = position.get('currency')
        reference = source_target_in_currency(conclusion.get('approved_project_target') or {}, currency, fx)
        price = position.get('observed_close')
        price_date = position.get('observed_market_date')
        if price is None:
            quote = (row.get('market') or {}).get('current_reference_quote') or {}
            if currency is not None and quote.get('currency') == currency:
                price = quote.get('observed_close')
                price_date = quote.get('observed_date')
        quantity = position.get('quantity')
        available_cash, conversion = cash_reference(cash, currency, fx)
        orders = conclusion.get('order_source') or {}
        order_exposure_known = orders.get('status') == 'VERIFIED' or bool(orders.get('complete_for_open_order_exposure'))
        scoped = row.get('owner_scoped_financial_result') or {}
        scoped_complete = scoped.get('status') == 'SCOPED_FINANCIAL_COMPLETE_NO_NEW_BUY'
        advice = {
            'currency': currency,
            'position_quantity': quantity,
            'price': price,
            'price_date': price_date,
            'reference_amount': reference['amount'] if reference else None,
            'shared_cash': cash.get(currency),
            'estimate_cash': str(available_cash) if available_cash is not None else None,
            'cash_conversion_scenario': conversion,
            'selected_stage': scoped['selected_stage'] if scoped_complete else conclusion.get('formal_stage'),
            'includes_open_order_exposure': order_exposure_known,
            'scenarios': [],
            'selected_estimate': None,
            'trade_authorization': 'NONE',
        }
        if reference is not None and price is not None and quantity is not None:
            active_orders = native_orders(root, orders, row['symbol'])
            with localcontext() as ctx:
                ctx.prec = 40
                for stage, percent in deployment.STAGE_RATE_PCT.items():
                    gap = deployment.calculate_position_gap(
                        project_target_position_amount=reference['amount'], target_rate=percent / 100,
                        confirmed_position_qty=quantity, canonical_valuation_price=price,
                        active_orders=active_orders)
                    # A positive estimate is bounded by one shared cash pool per
                    # comparison. Scenarios do not reserve it or allocate it.
                    amount = gap.positive_deployment_gap if gap.positive_deployment_gap == 0 else (
                        min(gap.positive_deployment_gap, available_cash) if available_cash is not None else None)
                    shares = ((amount / Decimal(str(price))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
                              if amount is not None else None)
                    scenario = {
                        'stage': stage, 'target_percent': str(percent),
                        'gap_amount': str(gap.positive_deployment_gap),
                        'estimate_amount': str(amount) if amount is not None else None,
                        'estimate_shares': str(shares) if shares is not None else None,
                    }
                    advice['scenarios'].append(scenario)
                    if stage == advice['selected_stage']:
                        advice['selected_estimate'] = scenario
        missing = []
        if reference is None:
            missing.append('allocation_reference_amount')
        if price is None:
            missing.append('observed_price')
        if quantity is None:
            missing.append('position_quantity')
        advice['missing_estimate_inputs'] = missing
        if scoped_complete:
            advice['selected_estimate'] = {
                'stage': scoped['selected_stage'],
                'gap_amount': '0',
                'estimate_amount': scoped['final_amount']['amount'],
                'estimate_shares': scoped['final_quantity'],
            }
        row['allocation_advice'] = advice
        row['result_digest'] = digest({k: v for k, v in row.items() if k != 'result_digest'})

    result['allocation_advice'] = {
        'assets_calculated': sum(bool(row['allocation_advice']['scenarios']) for row in result['positions']),
        'shared_cash_by_currency': cash,
        'scenarios_use_same_cash_independently': True,
        'fees_and_broker_lot_sizes_included': False,
        'trade_authorization': 'NONE',
    }
    result['report_digest'] = digest({k: v for k, v in result.items() if k != 'report_digest'})
    return result
